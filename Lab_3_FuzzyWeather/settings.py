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
