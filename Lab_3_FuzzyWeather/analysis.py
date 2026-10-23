"""Очистка, сезонные статистики и описательные отклонения погоды."""
from pathlib import Path
import numpy as np
import pandas as pd
from api_client import read_json
from settings import CITIES, START_DATE, END_DATE, VARIABLES, season_of

HOURLY_FIELDS = {
    "temperature_2m": "temperature", "relative_humidity_2m": "humidity",
    "wind_speed_10m": "wind",
}


def parse_history(city, data):
    hourly = data.get("hourly", {})
    units = data.get("hourly_units", {})
    if units.get("wind_speed_10m") != "m/s":
        raise ValueError("Исторический ветер должен быть в м/с, не в км/ч.")
    if units.get("temperature_2m") != "°C" or units.get("relative_humidity_2m") != "%":
        raise ValueError("Неверные единицы температуры или влажности.")
    if data.get("timezone") != "Europe/Moscow":
        raise ValueError("История должна использовать часовой пояс Europe/Moscow.")
    required = ["time", *HOURLY_FIELDS]
    if not all(isinstance(hourly.get(k), list) for k in required):
        raise ValueError("Нет обязательных почасовых массивов.")
    if len({len(hourly[k]) for k in required}) != 1:
        raise ValueError("Длины почасовых массивов не совпадают.")
    frame = pd.DataFrame({k: hourly[k] for k in required}).rename(columns=HOURLY_FIELDS)
    frame["time"] = pd.to_datetime(frame["time"], errors="raise")
    if frame["time"].duplicated().any():
        raise ValueError("Обнаружены повторяющиеся временные метки.")
    frame = frame.sort_values("time")
    for col in VARIABLES:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    bad = (~np.isfinite(frame[VARIABLES]).all(axis=1)
           | ~frame["temperature"].between(-60, 60)
           | ~frame["humidity"].between(0, 100)
           | ~frame["wind"].between(0, 60))
    quality = {"city": city, "received": len(frame), "excluded": int(bad.sum())}
    frame = frame.loc[~bad].copy()
    if frame.empty:
        raise ValueError("После проверки не осталось наблюдений.")
    frame["city"] = city
    frame["season"] = [season_of(int(m)) for m in frame["time"].dt.month]
    quality["valid"] = len(frame)
    quality["first"] = frame["time"].min().isoformat()
    quality["last"] = frame["time"].max().isoformat()
    return frame, quality


def load_history(folder):
    frames, quality = [], []
    expected = pd.date_range(START_DATE, END_DATE + " 23:00", freq="h")
    for city in CITIES:
        frame, info = parse_history(city, read_json(Path(folder) / "history" / f"{city}.json"))
        missing = len(expected.difference(pd.DatetimeIndex(frame["time"])))
        outside = len(pd.DatetimeIndex(frame["time"]).difference(expected))
        info.update(expected=len(expected), missing_hours=missing, outside_period=outside,
                    coverage=round((len(expected) - missing) / len(expected), 6))
        if outside or missing > 0.05 * len(expected):
            raise ValueError("Период истории неверен или отсутствует больше 5% часов.")
        frames.append(frame)
        quality.append(info)
    return pd.concat(frames, ignore_index=True), quality


def seasonal_stats(frame):
    grouped = frame.groupby(["city", "season"], observed=True)
    table = grouped.agg(
        n=("temperature", "size"),
        temperature_mean=("temperature", "mean"),
        temperature_std=("temperature", "std"),
        temperature_min=("temperature", "min"),
        temperature_max=("temperature", "max"),
        humidity_mean=("humidity", "mean"), humidity_std=("humidity", "std"),
        wind_mean=("wind", "mean"), wind_std=("wind", "std"),
    ).reset_index()
    if not np.isfinite(table.select_dtypes("number")).all().all():
        raise ValueError("Недостаточно наблюдений для сезонной статистики.")
    return table


def anomaly(value, mean, std):
    """|z|>2: учебный порог, НЕ вероятность и НЕ официальный прогноз."""
    if not all(np.isfinite(x) for x in (value, mean, std)) or std < 0:
        raise ValueError("Некорректные параметры отклонения.")
    delta = float(value - mean)
    if std == 0:
        return {"delta": delta, "z": None,
                "label": "нулевая дисперсия: z не определён", "flag": None}
    z = delta / std
    return {"delta": delta, "z": float(z), "flag": bool(abs(z) > 2),
            "label": "выше типичного диапазона" if z > 2 else
                     "ниже типичного диапазона" if z < -2 else "в пределах ±2σ"}
