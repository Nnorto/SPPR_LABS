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
