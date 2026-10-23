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
