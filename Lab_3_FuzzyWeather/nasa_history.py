"""История NASA POWER / MERRA-2. Исходные ответы отдельно от нормализации."""
from datetime import datetime, timezone
from pathlib import Path
import time
import pandas as pd
from api_client import request_json, save_json, read_json
from settings import CITIES, START_DATE, END_DATE, TIMEZONE

NASA_URL = "https://power.larc.nasa.gov/api/temporal/hourly/point"
DOC_URL = "https://power.larc.nasa.gov/docs/services/api/temporal/hourly/"


def normalize_nasa(parts):
    rows = []
    for data in parts:
        header = data.get("header", {})
        if header.get("time_standard") != "UTC":
            raise ValueError("NASA POWER должен возвращать UTC, не LST.")
        expected = {"T2M": "C", "RH2M": "%", "WS10M": "m/s"}
        if any(data["parameters"][k]["units"] != u for k, u in expected.items()):
            raise ValueError("Неожиданные единицы NASA POWER.")
        series = data["properties"]["parameter"]
        if any(set(series[k]) != set(series["T2M"]) for k in expected):
            raise ValueError("Временные метки параметров NASA не совпадают.")
        fill = header.get("fill_value", -999)
        for stamp in series["T2M"]:
            values = [None if series[k][stamp] == fill else series[k][stamp] for k in expected]
            rows.append([stamp, *values])
    frame = pd.DataFrame(rows, columns=["time", "temperature_2m",
                                       "relative_humidity_2m", "wind_speed_10m"])
    frame["time"] = pd.to_datetime(frame["time"], format="%Y%m%d%H", utc=True)
    frame["time"] = frame["time"].dt.tz_convert(TIMEZONE).dt.tz_localize(None)
    frame = frame.sort_values("time")
    if frame["time"].duplicated().any():
        raise ValueError("Дубли при объединении исходных годов NASA.")
    frame = frame[frame["time"].between(START_DATE, END_DATE + " 23:00")]
    hourly = {"time": frame["time"].dt.strftime("%Y-%m-%dT%H:%M").tolist()}
    for col in frame.columns[1:]:
        hourly[col] = [None if pd.isna(v) else float(v) for v in frame[col]]
    return {
        "_provenance": "NORMALIZED NASA POWER / MERRA-2; NOT an Open-Meteo response",
        "timezone": TIMEZONE,
        "hourly_units": {"temperature_2m": "°C", "relative_humidity_2m": "%",
                         "wind_speed_10m": "m/s"},
        "hourly": hourly,
    }


def fetch_nasa_history(folder):
    folder = Path(folder)
    for city, info in CITIES.items():
        parts, references = [], []
        for year in range(2020, 2026):
            start = "20201231" if year == 2020 else f"{year}0101"
            target = folder / "history" / "nasa_raw" / f"{city}_{year}.json"
            params = {
                "latitude": info["lat"], "longitude": info["lon"],
                "parameters": "T2M,RH2M,WS10M", "community": "RE",
                "start": start, "end": f"{year}1231", "format": "JSON", "time-standard": "UTC",
            }
            if target.exists():
                raw = read_json(target)
            else:
                print(f"NASA POWER: {info['name']}, {year}", flush=True)
                raw = request_json(NASA_URL, params)
                save_json(target, raw)
                save_json(target.with_suffix(".meta.json"), {
                    "url": NASA_URL, "parameters": params, "documentation": DOC_URL,
                    "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                })
                time.sleep(0.5)
            parts.append(raw)
            references.append(str(target.relative_to(folder)))
        save_json(folder / "history" / f"{city}.json", normalize_nasa(parts))
        save_json(folder / "history" / f"{city}.meta.json", {
            "provider": "NASA POWER / MERRA-2", "documentation": DOC_URL,
            "normalized": True, "raw_files": references,
            "start_date": START_DATE, "end_date": END_DATE,
            "note": "Open-Meteo недоступен из среды подготовки: дневной лимит API.",
        })


if __name__ == "__main__":
    from settings import ROOT
    fetch_nasa_history(ROOT / "data")
