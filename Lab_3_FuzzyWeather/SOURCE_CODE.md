# Полный листинг лабораторной №3

Код соответствует приложенным `.py`-файлам. Ключи и пользовательская конфигурация не включены.

## analysis.py

```python
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
```

## api_client.py

```python
"""API, валидация и кэширование. API-ключ не печатается и не логируется."""
from datetime import datetime, timezone
import json
import logging
import math
from pathlib import Path
import time
import requests
from settings import ARCHIVE_URL, CURRENT_URL, CITIES, START_DATE, END_DATE, TIMEZONE


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False),
                    encoding="utf-8")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def request_json(url, params, session=None, retries=2):
    session = session or requests.Session()
    for attempt in range(retries + 1):
        try:
            response = session.get(url, params=params, timeout=(10, 65))
        except requests.RequestException:
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError("Сетевая ошибка или тайм-аут; проверьте соединение.") from None
        if response.status_code == 429 or response.status_code >= 500:
            if response.status_code == 429:
                try:
                    reason = response.json().get("reason", "")
                except (ValueError, AttributeError):
                    reason = ""
                if isinstance(reason, str) and "daily" in reason.lower():
                    raise RuntimeError("Дневной лимит API исчерпан. Повторите завтра или выберите другой источник.")
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
        if response.status_code != 200:
            # Не вызываем raise_for_status: сообщение requests содержит URL с appid.
            raise RuntimeError(f"HTTP {response.status_code}: запрос API не выполнен.")
        try:
            data = response.json()
        except ValueError:
            raise RuntimeError("API вернул некорректный JSON.") from None
        if not isinstance(data, dict):
            raise RuntimeError("Корень JSON должен быть объектом.")
        if data.get("error") is True or str(data.get("cod", "200")) not in ("200",):
            raise RuntimeError("API сообщил об ошибке; проверьте доступ и параметры.")
        return data
    raise RuntimeError("Не удалось получить ответ API.")


def fetch_history(folder, session=None):
    """Один запрос на город, явная модель ERA5, ветер обязательно в м/с."""
    folder = Path(folder)
    for city, info in CITIES.items():
        target = folder / "history" / f"{city}.json"
        metadata = target.with_suffix(".meta.json")
        if target.exists() and metadata.exists() and "Open-Meteo" in read_json(metadata).get("provider", ""):
            logging.info("История %s: существующий кэш", city)
            continue
        params = {
            "latitude": info["lat"], "longitude": info["lon"],
            "start_date": START_DATE, "end_date": END_DATE,
            "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m",
            "wind_speed_unit": "ms", "temperature_unit": "celsius",
            "timezone": TIMEZONE, "models": "era5",
        }
        print("История:", info["name"], flush=True)
        data = request_json(ARCHIVE_URL, params, session=session)
        # Сначала сохраняется оригинальный ответ, затем метаданные отдельно.
        save_json(target, data)
        save_json(target.with_suffix(".meta.json"), {
            "provider": "Open-Meteo Historical Weather API / ERA5",
            "documentation": "https://open-meteo.com/en/docs/historical-weather-api",
            "url": ARCHIVE_URL, "parameters": params,
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "note": "Реанализ на сетке, не прямые измерения городской метеостанции.",
        })


def fetch_current(folder, api_key, session=None, proxy_auth=False):
    if not api_key and not proxy_auth:
        raise ValueError("Нет OpenWeatherMap API-ключа. Выполните setup_config.py.")
    folder = Path(folder)
    for city, info in CITIES.items():
        params = {"lat": info["lat"], "lon": info["lon"], "units": "metric", "lang": "ru"}
        if api_key:
            params["appid"] = api_key
        print("Текущая погода:", info["name"], flush=True)
        data = request_json(CURRENT_URL, params, session=session)
        parse_current(city, data)  # Не сохраняем неполный ответ как успешный.
        target = folder / "current" / f"{city}.json"
        save_json(target, data)
        save_json(target.with_suffix(".meta.json"), {
            "provider": "OpenWeatherMap Current Weather Data",
            "documentation": "https://openweathermap.org/current",
            "url": CURRENT_URL,
            "parameters": {k: v for k, v in params.items() if k != "appid"},
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        })


def valid_number(value, low, high, name):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not low <= value <= high):
        raise ValueError(f"Недопустимое поле {name}: допустимо {low}..{high}.")
    return float(value)


def parse_current(city, data):
    """dt является временем наблюдения API, не временем запуска программы."""
    try:
        if str(data.get("cod", "200")) != "200":
            raise ValueError("OpenWeatherMap сообщил об ошибке.")
        temp = valid_number(data["main"]["temp"], -60, 60, "temp")
        humidity = valid_number(data["main"]["humidity"], 0, 100, "humidity")
        wind = valid_number(data["wind"]["speed"], 0, 60, "wind.speed")
        stamp = valid_number(data["dt"], 0, 4102444800, "dt")
        observed = datetime.fromtimestamp(stamp, timezone.utc)
    except (KeyError, TypeError):
        raise ValueError("Отсутствуют обязательные поля текущей погоды.") from None
    return {
        "city": city, "temperature": temp, "humidity": humidity, "wind": wind,
        "observed_at_utc": observed.isoformat(),
        "description": (data.get("weather") or [{}])[0].get("description", ""),
    }
```

## architecture.py

```python
"""Схема из общей геометрии: редактируемый draw.io и PNG для отчёта."""
from pathlib import Path
import xml.etree.ElementTree as ET
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from settings import ROOT

NODES = {
    "nasa": (40, 45, 300, 85, "NASA POWER / MERRA-2\nИстория, 2021–2025"),
    "meteo": (390, 45, 300, 85, "Open-Meteo / ERA5\nАльтернативный адаптер"),
    "owm": (1040, 45, 300, 85, "OpenWeatherMap\nТекущие наблюдения + ключ"),
    "history": (215, 220, 300, 85, "JSON → проверка единиц\nUTC → Europe/Moscow"),
    "current": (1040, 220, 300, 85, "JSON → температура,\nвлажность, ветер, время"),
    "expert": (665, 220, 300, 85, "База знаний\n7 общих + 1 правило города"),
    "norms": (215, 395, 300, 85, "Сезонные статистики\nСреднее, s, min, max"),
    "fuzzy": (665, 395, 300, 110, "Мамдани: фаззификация\nИ/ИЛИ → активация\nmax → центр тяжести"),
    "anomaly": (1040, 470, 300, 85, "Сравнение с сезоном\nΔ и z; учебный порог |z|>2"),
    "result": (665, 620, 300, 85, "Индекс комфорта\n+ предупреждения и советы"),
    "table": (215, 785, 300, 70, "CSV / JSON / Markdown\nТаблицы и трассировка"),
    "plots": (665, 785, 300, 70, "PNG: термы, профили,\nвременной ряд, результат"),
    "doc": (1040, 785, 300, 70, "Отчёт и защита\nИсходники + скриншоты"),
}
EDGES = [
    ("nasa", "history"), ("meteo", "history"), ("owm", "current"),
    ("history", "norms"), ("norms", "fuzzy"), ("expert", "fuzzy"),
    ("current", "fuzzy"), ("current", "anomaly"), ("norms", "anomaly"),
    ("fuzzy", "result"), ("anomaly", "result"),
    ("result", "table"), ("result", "plots"), ("result", "doc"),
]


def anchors(a, b):
    x, y, w, h, _ = NODES[a]
    X, Y, W, H, _ = NODES[b]
    if b == "anomaly" and a == "norms":
        return (x+w/2, y+h), (X, Y+H/2)
    if abs((x+w/2)-(X+W/2)) > 300 and abs(y-Y) < 170:
        return ((x+w, y+h/2), (X, Y+H/2)) if x<X else ((x, y+h/2), (X+W, Y+H/2))
    return (x+w/2, y+h), (X+W/2, Y)


def create(folder=ROOT):
    folder = Path(folder)
    root = ET.Element("mxfile", host="app.diagrams.net")
    diagram = ET.SubElement(root, "diagram", name="Архитектура лабораторной №3")
    model = ET.SubElement(diagram, "mxGraphModel", page="1", pageWidth="1400", pageHeight="900")
    graph = ET.SubElement(model, "root")
    ET.SubElement(graph, "mxCell", id="0")
    ET.SubElement(graph, "mxCell", id="1", parent="0")
    fig, ax = plt.subplots(figsize=(14, 9), layout="constrained")
    ax.set_xlim(0, 1400)
    ax.set_ylim(900, 0)
    ax.axis("off")
    for node, (x, y, w, h, text) in NODES.items():
        cell = ET.SubElement(graph, "mxCell", id=node, value=text, vertex="1", parent="1",
                             style="rounded=1;whiteSpace=wrap;html=0;fillColor=#F7F6F2;strokeColor=#01696F;fontSize=17;")
        ET.SubElement(cell, "mxGeometry", x=str(x), y=str(y), width=str(w), height=str(h),
                      attrib={"as": "geometry"})
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle="round,pad=0,rounding_size=8",
                                   facecolor="#F7F6F2",edgecolor="#01696F"))
        ax.text(x+w/2,y+h/2,text,ha="center",va="center",fontsize=11)
    for i, (a, b) in enumerate(EDGES):
        edge = ET.SubElement(graph, "mxCell", id=f"e{i}", edge="1", parent="1",
                             source=a, target=b, style="edgeStyle=orthogonalEdgeStyle;endArrow=block;")
        ET.SubElement(edge, "mxGeometry", relative="1", attrib={"as": "geometry"})
        start, end = anchors(a, b)
        if (a,b) == ("norms","anomaly"):
            points = [start, (start[0], 580), (1010,580), (1010,end[1]), end]
            for p,q in zip(points[:-2],points[1:-1]):
                ax.plot([p[0],q[0]],[p[1],q[1]],color="#555",lw=1)
            ax.add_patch(FancyArrowPatch(points[-2],points[-1],arrowstyle="-|>",
                                        mutation_scale=12,color="#555"))
        else:
            ax.add_patch(FancyArrowPatch(start,end,arrowstyle="-|>",mutation_scale=12,
                                        color="#555",linestyle="--" if a=="meteo" else "-"))
    fig.savefig(folder/"architecture.png",dpi=170,bbox_inches="tight")
    plt.close(fig)
    ET.ElementTree(root).write(folder/"architecture.drawio",encoding="utf-8",xml_declaration=True)


if __name__ == "__main__":
    create()
```

## charts.py

```python
"""Статические графики на основе расчётов, без сетевых обращений."""
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from settings import CITIES, SEASONS, SEASON_NAMES
from fuzzy_model import TERM_RU

COLORS = ["#20808D", "#A84B2F", "#1B474D", "#944454", "#848456"]
LINESTYLES = ["-", "--", "-.", ":", (0, (5, 1))]


def configure():
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 11,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.alpha": .18, "figure.dpi": 140,
        "savefig.facecolor": "white",
    })


def save(fig, path):
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def plot_history(frame, norms, folder, provider):
    configure()
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.6), layout="constrained")
    for ax, (metric, label) in zip(axes, [("temperature", "Температура, °C"),
                                        ("humidity", "Влажность, %"), ("wind", "Ветер, м/с")]):
        for i, (city, info) in enumerate(CITIES.items()):
            sub = norms[norms.city == city].set_index("season").loc[SEASONS]
            ax.plot(range(4), sub[metric + "_mean"], marker=["o", "s", "^"][i],
                    color=COLORS[i], linestyle=LINESTYLES[i], label=info["name"])
        ax.set_xticks(range(4), [SEASON_NAMES[s] for s in SEASONS], rotation=25)
        ax.set_ylabel(label)
    axes[0].legend(fontsize=9)
    fig.suptitle(f"Сезонные средние за 2021–2025 годы\n{provider}; учебная пятилетняя база",
                 fontsize=13)
    save(fig, folder / "seasonal_profiles.png")
    fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True, layout="constrained")
    for ax, (city, info), color in zip(axes, CITIES.items(), COLORS):
        daily = frame[frame.city == city].set_index("time")["temperature"].resample("D").mean()
        smooth = daily.rolling(30, min_periods=30).mean()
        ax.plot(daily.index, daily, color="#a8adad", lw=.5, label="Среднее за сутки")
        ax.plot(smooth.index, smooth, color=color, lw=1.5, label="Среднее за 30 суток")
        ax.set_title(info["name"], loc="left")
        ax.set_ylabel("°C")
        ax.legend(loc="upper right", fontsize=9)
    fig.suptitle("Сезонные колебания температуры, 2021–2025\nСглаживание не доказывает долгосрочный климатический тренд",
                 fontsize=13)
    save(fig, folder / "temperature_trends.png")


def plot_memberships(model, folder):
    configure()
    fig, axes = plt.subplots(2, 2, figsize=(12, 8.3), layout="constrained")
    labels = {"temperature": "Температура, °C", "humidity": "Влажность, %",
              "wind": "Ветер, м/с", "comfort": "Условный комфорт, 0–100"}
    for ax, (name, var) in zip(axes.flat, model.variables.items()):
        for i, (term, obj) in enumerate(var.terms.items()):
            label = {"far_below": "намного ниже", "below": "ниже", "typical": "типично",
                     "above": "выше", "far_above": "намного выше"}.get(term, TERM_RU[term])
            ax.plot(var.universe, obj.mf, color=COLORS[i], linestyle=LINESTYLES[i],
                    label=label, lw=1.8)
        ax.set_xlabel(labels[name])
        ax.set_ylabel("Степень принадлежности μ")
        ax.set_ylim(-.03, 1.08)
        if name == "temperature":
            ax.set_xlim(max(-60, model.mean-3*model.scale), min(60, model.mean+3*model.scale))
        if name == "wind":
            ax.set_xlim(0, 25)
        ax.legend(fontsize=8, loc="upper right")
    fig.suptitle(
        f"{CITIES[model.city]['name']}: {SEASON_NAMES[model.season].lower()}\n"
        f"Температурные термы: среднее {model.mean:.2f} °C; масштаб {model.scale:.2f} °C",
        fontsize=13)
    save(fig, Path(folder) / f"membership_{model.city}.png")


def plot_results(results, folder, mode):
    configure()
    fig, ax = plt.subplots(figsize=(9, 4.8), layout="constrained")
    names = [CITIES[r["city"]]["name"] for r in results]
    values = [r["fuzzy"]["comfort"] for r in results]
    bars = ax.barh(names, values, color=COLORS[:len(names)], height=.5)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Условный индекс комфорта (не медицинский показатель)")
    for bar, val in zip(bars, values):
        ax.text(min(val + 2, 93), bar.get_y()+bar.get_height()/2, f"{val:.1f}",
                va="center", fontsize=12)
    tag = "Сохранённые ответы OpenWeatherMap" if mode == "cached" else "Исторический пример, НЕ текущая погода"
    fig.suptitle(f"Результат нечёткого вывода Мамдани\n{tag}", fontsize=13)
    save(fig, Path(folder) / "comfort_comparison.png")
```

## fuzzy_model.py

```python
"""Настоящий Mamdani: min для AND, max для OR/аккумуляции, centroid."""
import numpy as np
import skfuzzy as fuzz
from skfuzzy import control as ctrl
from api_client import valid_number
from settings import CITIES

TERM_RU = {
    "far_below": "значительно холоднее сезонного среднего",
    "below": "прохладнее сезонного среднего", "typical": "типично для сезона",
    "above": "теплее сезонного среднего",
    "far_above": "значительно теплее сезонного среднего",
    "dry": "низкая влажность", "moderate": "умеренная влажность",
    "wet": "высокая влажность", "light": "слабый ветер",
    "breezy": "умеренный ветер", "strong": "сильный ветер",
    "poor": "низкий комфорт", "fair": "средний комфорт", "good": "высокий комфорт",
}


class WeatherFuzzy:
    def __init__(self, city, season, mean, std):
        if city not in CITIES or not np.isfinite(mean) or not -40 < mean < 40:
            raise ValueError("Некорректный город или средняя температура.")
        if not np.isfinite(std) or std < 0:
            raise ValueError("Некорректное стандартное отклонение.")
        self.city, self.season = city, season
        self.mean, self.scale = float(mean), max(float(std), 1.0)
        if mean - 2 * self.scale <= -60 or mean + 2 * self.scale >= 60:
            raise ValueError("Сезонные термы выходят за универсум.")
        t = ctrl.Antecedent(np.linspace(-60, 60, 481), "temperature")
        h = ctrl.Antecedent(np.arange(101), "humidity")
        w = ctrl.Antecedent(np.linspace(0, 60, 241), "wind")
        c = ctrl.Consequent(np.linspace(0, 100, 1001), "comfort", defuzzify_method="centroid")
        m, s = self.mean, self.scale
        t["far_below"] = fuzz.trapmf(t.universe, [-60, -60, m-2*s, m-s])
        t["below"] = fuzz.trimf(t.universe, [m-2*s, m-s, m])
        t["typical"] = fuzz.trimf(t.universe, [m-s, m, m+s])
        t["above"] = fuzz.trimf(t.universe, [m, m+s, m+2*s])
        t["far_above"] = fuzz.trapmf(t.universe, [m+s, m+2*s, 60, 60])
        h["dry"] = fuzz.trapmf(h.universe, [0, 0, 25, 45])
        h["moderate"] = fuzz.trimf(h.universe, [25, 55, 85])
        h["wet"] = fuzz.trapmf(h.universe, [65, 85, 100, 100])
        w["light"] = fuzz.trapmf(w.universe, [0, 0, 2, 5])
        w["breezy"] = fuzz.trimf(w.universe, [2, 7, 12])
        w["strong"] = fuzz.trapmf(w.universe, [8, 15, 60, 60])
        c["poor"] = fuzz.trapmf(c.universe, [0, 0, 20, 40])
        c["fair"] = fuzz.trimf(c.universe, [25, 50, 75])
        c["good"] = fuzz.trapmf(c.universe, [60, 80, 100, 100])
        definitions = [
            ("R1", t["far_below"], "poor", "Сильное похолодание относительно сезона → низкий комфорт."),
            ("R2", t["far_above"], "poor", "Сильное потепление относительно сезона → низкий комфорт."),
            ("R3", t["below"], "fair", "Прохладнее обычного → средний комфорт."),
            ("R4", t["above"], "fair", "Теплее обычного → средний комфорт."),
            ("R5", t["typical"] & h["moderate"] & w["light"], "good",
             "Типичная температура, умеренная влажность и слабый ветер → высокий комфорт."),
            ("R6", t["typical"] & (h["dry"] | h["wet"] | w["breezy"]), "fair",
             "Типичная температура, но крайняя влажность или умеренный ветер → средний комфорт."),
            ("R7", w["strong"], "poor", "Сильный ветер → низкий комфорт."),
        ]
        if city == "spb":
            extra = (h["wet"] & (w["breezy"] | w["strong"]),
                     "Петербург: высокая влажность и ветер → низкий комфорт.")
        elif city == "moscow":
            extra = (t["above"] & h["wet"],
                     "Москва: теплее сезонного среднего и влажно → низкий комфорт.")
        else:
            extra = (t["below"] & (w["breezy"] | w["strong"]),
                     "Казань: прохладнее сезонного среднего и ветер → низкий комфорт.")
        definitions.append(("R8", extra[0], "poor", extra[1]))
        self.rule_specs = [{"id": i, "output": o, "text": text} for i, _, o, text in definitions]
        self.rules = [ctrl.Rule(antecedent, c[output], label=i)
                      for i, antecedent, output, _ in definitions]
        self.system = ctrl.ControlSystem(self.rules)
        self.variables = {"temperature": t, "humidity": h, "wind": w, "comfort": c}

    def evaluate(self, temperature, humidity, wind):
        values = {
            "temperature": valid_number(temperature, -60, 60, "temperature"),
            "humidity": valid_number(humidity, 0, 100, "humidity"),
            "wind": valid_number(wind, 0, 60, "wind"),
        }
        simulation = ctrl.ControlSystemSimulation(self.system, clip_to_bounds=False)
        for key, value in values.items():
            simulation.input[key] = value
        simulation.compute()
        if "comfort" not in simulation.output:
            raise RuntimeError("Ни одно правило не активировано.")
        score = float(simulation.output["comfort"])
        memberships = {}
        for variable, value in values.items():
            var = self.variables[variable]
            memberships[variable] = {
                term: float(fuzz.interp_membership(var.universe, obj.mf, value))
                for term, obj in var.terms.items()
            }
        trace = [{**spec, "activation": float(rule.aggregate_firing[simulation] or 0)}
                 for spec, rule in zip(self.rule_specs, self.rules)]
        return {
            "comfort": score,
            "comfort_label": "низкий" if score < 40 else "средний" if score < 70 else "высокий",
            "memberships": memberships, "rules": trace,
            "temperature_scale": self.scale, "temperature_mean": self.mean,
        }


def recommendations(city, values, analysis, anomalies):
    """Защитные рекомендации отдельно от условного индекса комфорта."""
    t, h, w = (values[k] for k in ("temperature", "humidity", "wind"))
    notes = []
    if w > 15:
        notes.append("Учебный флаг сильного ветра: отложите длительную прогулку, проверьте предупреждения служб.")
    if t < -25:
        notes.append("Сильный мороз: сократите пребывание на улице, используйте тёплые слои одежды.")
    if t > 35:
        notes.append("Сильная жара: избегайте длительной нагрузки на солнце, проверьте официальные рекомендации.")
    if city == "spb" and h > 85 and t < 5:
        notes.append("Сыро и холодно: предусмотрите ветрозащитный и непромокаемый верхний слой.")
    if city == "moscow" and t > 25:
        notes.append("Для прогулки выбирайте затенённый маршрут; это учебное правило для Москвы.")
    if city == "kazan" and t < -10:
        notes.append("Для Казани при морозе добавлен совет защитить лицо и руки от ветра.")
    if h < 30:
        notes.append("Низкая относительная влажность: учитывайте сухость воздуха.")
    if h > 85:
        notes.append("Высокая влажность не доказывает наличие дождя: проверьте отдельный прогноз осадков.")
    for variable, item in anomalies.items():
        if item["flag"]:
            notes.append(f"{variable}: отклонение {item['z']:+.2f}σ от среднего за сезон 2021–2025.")
    if not notes and analysis["comfort"] >= 70:
        notes.append("По учебной модели условия относительно комфортны; проверьте прогноз перед выходом.")
    if not notes:
        notes.append("Учебная модель советует одежду по температуре и короткую прогулку по самочувствию.")
    notes.append("Это учебная экспертная система, не прогноз опасных явлений и не медицинская рекомендация.")
    return notes
```

## main.py

```python
"""Конвейер анализа. По умолчанию читает сохранённые ответы OpenWeatherMap."""
import argparse
from datetime import datetime, timezone
import logging
from pathlib import Path
import sys
from zoneinfo import ZoneInfo
import pandas as pd
from api_client import fetch_current, fetch_history, parse_current, read_json, save_json
from analysis import load_history, seasonal_stats, anomaly
from fuzzy_model import WeatherFuzzy, TERM_RU, recommendations
from charts import plot_history, plot_memberships, plot_results
from settings import ROOT, CITIES, TIMEZONE, VARIABLES, season_of, SEASON_NAMES


def analyze_observation(observation, norms, mode):
    city = observation["city"]
    observed = datetime.fromisoformat(observation["observed_at_utc"])
    season = season_of(observed.astimezone(ZoneInfo(TIMEZONE)).month)
    selected = norms[(norms.city == city) & (norms.season == season)]
    if len(selected) != 1:
        raise ValueError("Нет однозначной сезонной нормы.")
    normal = selected.iloc[0]
    model = WeatherFuzzy(city, season, normal.temperature_mean, normal.temperature_std)
    fuzzy = model.evaluate(*(observation[k] for k in VARIABLES))
    deviations = {key: anomaly(observation[key], normal[key+"_mean"], normal[key+"_std"])
                  for key in VARIABLES}
    result = {
        **observation, "mode": mode, "season": season,
        "baseline": {k: float(normal[k]) for k in normal.index if k not in ("city", "season")},
        "fuzzy": fuzzy, "anomalies": deviations,
        "recommendations": recommendations(city, observation, fuzzy, deviations),
        "age_hours_at_processing": (datetime.now(timezone.utc)-observed).total_seconds()/3600,
    }
    return result, model


def run(data_folder, output, historical_demo=False):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    logging.basicConfig(filename=output/"run.log", encoding="utf-8", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", force=True)
    history, quality = load_history(data_folder)
    norms = seasonal_stats(history)
    norms.to_csv(output/"seasonal_norms.csv", index=False, encoding="utf-8-sig")
    save_json(output/"data_quality.json", quality)
    mode = "historical-demo" if historical_demo else "cached"
    print("Режим:", mode, flush=True)
    print("Период сезонной базы: 2021–2025, не 30-летняя климатическая норма.", flush=True)
    providers = {read_json(Path(data_folder)/"history"/f"{c}.meta.json")["provider"] for c in CITIES}
    provider = " / ".join(sorted(providers))
    figures = output / "figures"
    plot_history(history, norms, figures, provider)
    results, concise = [], []
    for city, info in CITIES.items():
        if historical_demo:
            last = history[history.city == city].iloc[-1]
            obs = {
                "city": city, **{k: float(last[k]) for k in VARIABLES},
                "observed_at_utc": last.time.tz_localize(TIMEZONE).tz_convert("UTC").isoformat(),
                "description": "Реальная последняя запись истории; НЕ текущая погода.",
            }
        else:
            obs = parse_current(city, read_json(Path(data_folder)/"current"/f"{city}.json"))
        result, model = analyze_observation(obs, norms, mode)
        results.append(result)
        plot_memberships(model, figures)
        row = {"city": info["name"], "season": SEASON_NAMES[result["season"]],
               "observed_at_utc": obs["observed_at_utc"],
               **{k: obs[k] for k in VARIABLES}, "comfort": result["fuzzy"]["comfort"]}
        for variable in VARIABLES:
            row.update({f"{variable}_{key}": result["anomalies"][variable][key]
                        for key in ("delta", "z", "label")})
        concise.append(row)
        print(f"{info['name']}: {obs['temperature']:.2f} °C; "
              f"{obs['humidity']:.0f}%; {obs['wind']:.2f} м/с; "
              f"комфорт {result['fuzzy']['comfort']:.1f}/100", flush=True)
        print("  Время данных UTC:", obs["observed_at_utc"], flush=True)
        if mode == "cached" and result["age_hours_at_processing"] > 6:
            print("  Кэш старше 6 часов. Для новой погоды используйте --refresh-current.", flush=True)
        print("  Температура:", result["anomalies"]["temperature"]["label"], flush=True)
        logging.info("%s %s mode=%s comfort=%.3f", city, obs["observed_at_utc"],
                     mode, result["fuzzy"]["comfort"])
    save_json(output/"analysis.json", results)
    pd.DataFrame(concise).to_csv(output/"comparison.csv", index=False, encoding="utf-8-sig")
    plot_results(results, figures, mode)
    write_result_report(output, results, provider)
    save_json(output/"manifest.json", {
        "mode": mode, "history_provider": provider, "baseline": "2021-01-01..2025-12-31",
        "run_at_utc": datetime.now(timezone.utc).isoformat(), "records": len(history),
        "method": "Mamdani min/max, centroid; conditional educational comfort 0..100",
    })
    print("Всего почасовых записей:", len(history), flush=True)
    print("Результаты:", output, flush=True)
    return results


def write_result_report(output, results, provider):
    lines = ["# Результаты анализа погоды", "",
             f"Источник истории: {provider}. Период: 2021–2025.", "",
             "Полные исходные ответы и метаданные находятся в папке data.",
             "Значения показывают конкретный момент данных, а не погоду в момент чтения отчёта.", ""]
    for row in results:
        lines += [f"## {CITIES[row['city']]['name']}", "",
                  f"Режим: `{row['mode']}`. Время UTC: `{row['observed_at_utc']}`.", "",
                  f"Температура {row['temperature']:.2f} °C; влажность {row['humidity']:.0f}%; "
                  f"ветер {row['wind']:.2f} м/с.", "",
                  f"Условный комфорт: {row['fuzzy']['comfort']:.2f}/100 "
                  f"({row['fuzzy']['comfort_label']}).", "",
                  "### Фаззификация", ""]
        for variable, terms in row["fuzzy"]["memberships"].items():
            text = "; ".join(f"{TERM_RU[t]}: {v:.3f}" for t, v in terms.items() if v > 0)
            lines += [f"- **{variable}:** {text}."]
        lines += ["", "### Активные правила", ""]
        for rule in row["fuzzy"]["rules"]:
            if rule["activation"] > 0:
                lines += [f"- **{rule['id']}:** {rule['text']} α={rule['activation']:.3f}."]
        lines += ["", "### Отклонения", ""]
        for variable, item in row["anomalies"].items():
            z = "не определён" if item["z"] is None else f"{item['z']:+.3f}"
            lines += [f"- **{variable}:** Δ={item['delta']:+.3f}, z={z}; {item['label']}."]
        lines += ["", "### Рекомендации", "", *["- "+s for s in row["recommendations"]], ""]
    (Path(output)/"RESULTS.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT/"data")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--historical-demo", action="store_true")
    parser.add_argument("--refresh-current", action="store_true")
    parser.add_argument("--download-history", choices=["nasa", "openmeteo"])
    args = parser.parse_args()
    try:
        if args.historical_demo and args.refresh_current:
            raise ValueError("Исторический пример нельзя обозначать как текущий.")
        if args.download_history == "nasa":
            from nasa_history import fetch_nasa_history
            fetch_nasa_history(args.data)
        elif args.download_history == "openmeteo":
            fetch_history(args.data)
        if args.refresh_current:
            config = read_json(ROOT/"config.json")
            key = config.get("openweather_api_key", "")
            if not isinstance(key, str) or not key or key.startswith("PUT_"):
                raise ValueError("Заполните OpenWeatherMap API key через setup_config.py.")
            fetch_current(args.data, key)
        if not args.historical_demo:
            absent = [c for c in CITIES if not (args.data/"current"/f"{c}.json").exists()]
            if absent:
                raise ValueError("Нет сохранённых ответов OpenWeatherMap. Запустите с --refresh-current "
                                 "или явно выберите --historical-demo.")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
        run(args.data, args.output or ROOT/"output"/stamp, args.historical_demo)
        return 0
    except (ValueError, RuntimeError, OSError, KeyError) as error:
        print("Ошибка:", error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

## nasa_history.py

```python
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
```

## settings.py

```python
"""Явные настройки исследования. Координаты: выбранные опорные точки городов."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CITIES = {
    "kazan": {"name": "Казань", "lat": 55.7961, "lon": 49.1064},
    "moscow": {"name": "Москва", "lat": 55.7558, "lon": 37.6173},
    "spb": {"name": "Санкт-Петербург", "lat": 59.9343, "lon": 30.3351},
}
SEASONS = ["winter", "spring", "summer", "autumn"]
SEASON_NAMES = dict(zip(SEASONS, ["Зима", "Весна", "Лето", "Осень"]))
START_DATE = "2021-01-01"
END_DATE = "2025-12-31"
TIMEZONE = "Europe/Moscow"
VARIABLES = ["temperature", "humidity", "wind"]
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
CURRENT_URL = "https://api.openweathermap.org/data/2.5/weather"


def season_of(month):
    if not isinstance(month, int) or isinstance(month, bool) or not 1 <= month <= 12:
        raise ValueError("Месяц должен быть целым числом от 1 до 12.")
    return ("winter" if month in (12, 1, 2) else "spring" if month <= 5
            else "summer" if month <= 8 else "autumn")
```

## setup_config.py

```python
"""Создаёт конфигурацию на личном Mac, не выполняя сетевых запросов."""
import getpass
import json
import os
from settings import ROOT

if __name__ == "__main__":
    path = ROOT / "config.json"
    if path.exists():
        raise SystemExit("config.json уже есть. При необходимости измените его локально.")
    key = getpass.getpass("OpenWeatherMap API key (ввод скрыт): ").strip()
    if not key:
        raise SystemExit("Пустой ключ. Конфигурация не создана.")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"openweather_api_key": key}, f, indent=2)
    print("config.json создан. Не отправляйте его с отчётом.")
```

## test_lab.py

```python
"""Локальные тесты не обращаются в сеть: python3 -m unittest -v."""
import copy
import math
import unittest
from unittest.mock import Mock, patch
import numpy as np
import skfuzzy as fuzz
from api_client import parse_current, request_json
from analysis import parse_history, seasonal_stats, anomaly
from fuzzy_model import WeatherFuzzy, recommendations
from settings import season_of
from nasa_history import normalize_nasa


def history_fixture():
    return {"timezone": "Europe/Moscow",
            "hourly_units": {"temperature_2m": "°C", "relative_humidity_2m": "%",
                             "wind_speed_10m": "m/s"},
            "hourly": {"time": ["2025-01-01T00:00", "2025-01-01T01:00"],
                       "temperature_2m": [0, 2], "relative_humidity_2m": [50, 70],
                       "wind_speed_10m": [1, 3]}}


class StatisticsTests(unittest.TestCase):
    def test_all_months(self):
        self.assertEqual([season_of(x) for x in range(1, 13)],
                         ["winter"]*2+["spring"]*3+["summer"]*3+["autumn"]*3+["winter"])

    def test_invalid_month(self):
        for month in [0, 13, 1.5, True]:
            with self.subTest(month=month), self.assertRaises(ValueError):
                season_of(month)

    def test_sample_std(self):
        frame, _ = parse_history("kazan", history_fixture())
        normal = seasonal_stats(frame).iloc[0]
        self.assertEqual(normal.temperature_mean, 1)
        self.assertAlmostEqual(normal.temperature_std, math.sqrt(2))

    def test_missing_excluded(self):
        data = history_fixture()
        data["hourly"]["temperature_2m"][0] = None
        frame, quality = parse_history("kazan", data)
        self.assertEqual(len(frame), 1)
        self.assertEqual(quality["excluded"], 1)

    def test_impossible_humidity_excluded(self):
        data = history_fixture()
        data["hourly"]["relative_humidity_2m"][0] = 101
        self.assertEqual(parse_history("kazan", data)[1]["excluded"], 1)

    def test_all_bad_rejected(self):
        data = history_fixture()
        data["hourly"]["wind_speed_10m"] = [-1, -2]
        with self.assertRaises(ValueError):
            parse_history("kazan", data)

    def test_wrong_wind_units(self):
        data = history_fixture()
        data["hourly_units"]["wind_speed_10m"] = "km/h"
        with self.assertRaises(ValueError):
            parse_history("kazan", data)

    def test_timezone(self):
        data = history_fixture()
        data["timezone"] = "UTC"
        with self.assertRaises(ValueError):
            parse_history("kazan", data)

    def test_duplicate_hours(self):
        data = history_fixture()
        data["hourly"]["time"][1] = data["hourly"]["time"][0]
        with self.assertRaises(ValueError):
            parse_history("kazan", data)

    def test_array_lengths(self):
        data = history_fixture()
        data["hourly"]["wind_speed_10m"] = [1]
        with self.assertRaises(ValueError):
            parse_history("kazan", data)

    def test_zscore(self):
        self.assertEqual(anomaly(13, 5, 2)["z"], 4)
        self.assertTrue(anomaly(13, 5, 2)["flag"])

    def test_two_sigma_boundary(self):
        self.assertFalse(anomaly(9, 5, 2)["flag"])

    def test_zero_std(self):
        self.assertIsNone(anomaly(9, 5, 0)["z"])

    def test_negative_std(self):
        with self.assertRaises(ValueError):
            anomaly(9, 5, -1)


class APITests(unittest.TestCase):
    def fixture(self):
        return {"cod": 200, "dt": 1760000000, "main": {"temp": 5, "humidity": 80},
                "wind": {"speed": 4}, "weather": [{"description": "тест"}]}

    def test_current_fields(self):
        row = parse_current("kazan", self.fixture())
        self.assertEqual(row["temperature"], 5)
        self.assertEqual(row["wind"], 4)
        self.assertIn("+00:00", row["observed_at_utc"])

    def test_missing_current_fields(self):
        with self.assertRaises(ValueError):
            parse_current("kazan", {})

    def test_invalid_numeric(self):
        for value in [float("nan"), float("inf"), "5", True, -100]:
            data = self.fixture()
            data["main"]["temp"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_current("kazan", data)

    def test_401_no_key_leak(self):
        response = Mock(status_code=401)
        session = Mock()
        session.get.return_value = response
        with self.assertRaisesRegex(RuntimeError, "HTTP 401") as caught:
            request_json("https://example.invalid", {"appid": "TEST_SECRET"}, session)
        self.assertNotIn("TEST_SECRET", str(caught.exception))
        self.assertEqual(session.get.call_count, 1)

    def test_429_retried(self):
        session = Mock()
        session.get.side_effect = [Mock(status_code=429), Mock(status_code=200, json=lambda: {})]
        with patch("api_client.time.sleep"):
            self.assertEqual(request_json("https://example.invalid", {}, session), {})
        self.assertEqual(session.get.call_count, 2)

    def test_non_json(self):
        session = Mock()
        session.get.return_value = Mock(status_code=200, json=Mock(side_effect=ValueError()))
        with self.assertRaisesRegex(RuntimeError, "JSON"):
            request_json("https://example.invalid", {}, session)

    def test_nasa_timezone_shift_and_fill(self):
        data = {"header": {"time_standard": "UTC", "fill_value": -999},
                "parameters": {"T2M": {"units": "C"}, "RH2M": {"units": "%"},
                               "WS10M": {"units": "m/s"}},
                "properties": {"parameter": {
                    "T2M": {"2020123121": 1, "2020123122": -999},
                    "RH2M": {"2020123121": 50, "2020123122": 60},
                    "WS10M": {"2020123121": 2, "2020123122": 3}}}}
        normalized = normalize_nasa([data])
        self.assertEqual(normalized["hourly"]["time"][0], "2021-01-01T00:00")
        self.assertIsNone(normalized["hourly"]["temperature_2m"][1])


class FuzzyTests(unittest.TestCase):
    def setUp(self):
        self.model = WeatherFuzzy("kazan", "autumn", 7, 7)

    def test_membership_ranges_and_no_gaps(self):
        for name, variable in self.model.variables.items():
            arrays = np.array([t.mf for t in variable.terms.values()])
            self.assertTrue(np.isfinite(arrays).all())
            self.assertTrue(((arrays >= 0) & (arrays <= 1)).all())
            self.assertTrue((arrays.max(axis=0) > 0).all(), name)

    def test_comfortable_case(self):
        self.assertGreater(self.model.evaluate(7, 55, 1)["comfort"], 70)

    def test_storm_lower(self):
        self.assertLess(self.model.evaluate(7, 55, 25)["comfort"],
                        self.model.evaluate(7, 55, 1)["comfort"])

    def test_grid_complete(self):
        for t in [-60, -25, 0, 7, 30, 60]:
            for h in [0, 55, 100]:
                for w in [0, 7, 60]:
                    result = self.model.evaluate(t, h, w)
                    self.assertTrue(0 <= result["comfort"] <= 100)

    def test_input_not_clipped(self):
        with self.assertRaises(ValueError):
            self.model.evaluate(61, 55, 0)

    def test_memberships_trace(self):
        result = self.model.evaluate(7, 55, 1)
        self.assertAlmostEqual(result["memberships"]["temperature"]["typical"], 1)
        self.assertEqual(len(result["rules"]), 8)
        self.assertEqual(result["rules"][4]["activation"], 1)

    def test_adapts_to_season(self):
        winter = WeatherFuzzy("kazan", "winter", -10, 6)
        summer = WeatherFuzzy("kazan", "summer", 20, 5)
        self.assertGreater(winter.evaluate(-10, 55, 0)["comfort"],
                           summer.evaluate(-10, 55, 0)["comfort"])

    def test_city_rule(self):
        spb = WeatherFuzzy("spb", "autumn", 7, 7)
        result = spb.evaluate(7, 95, 7)
        self.assertGreater(result["rules"][7]["activation"], 0)

    def test_constant_history_scale(self):
        self.assertEqual(WeatherFuzzy("kazan", "winter", -5, 0).scale, 1)

    def test_independent_centroid(self):
        result = self.model.evaluate(0, 80, 7)
        var = self.model.variables["comfort"]
        aggregate = np.zeros_like(var.universe)
        for rule in result["rules"]:
            aggregate = np.maximum(aggregate, np.minimum(rule["activation"], var[rule["output"]].mf))
        direct = fuzz.defuzz(var.universe, aggregate, "centroid")
        self.assertAlmostEqual(direct, result["comfort"], delta=.03)

    def test_guard_recommendation(self):
        row = {"temperature": -30, "humidity": 95, "wind": 20}
        result = self.model.evaluate(-30, 95, 20)
        notes = recommendations("kazan", row, result, {})
        self.assertTrue(any("мороз" in n for n in notes))
        self.assertTrue(any("ветра" in n for n in notes))


if __name__ == "__main__":
    unittest.main()
```
