"""Чтение конфигурации. AppID не находится в исходном коде."""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_config(path=ROOT / "config.json"):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError("Нет config.json. Выполните: python3 setup_config.py") from None
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ValueError("Не удалось прочитать config.json: проверьте UTF-8 и JSON.") from None
    if not isinstance(data, dict):
        raise ValueError("config.json должен содержать JSON-объект.")
    key = data.get("appid")
    if not isinstance(key, str) or not key.strip() or key == "PUT_YOUR_APPID_HERE":
        raise ValueError("В config.json не заполнен appid.")
    data["appid"] = key.strip()
    for field, default, lower, upper in [
        ("timeout_seconds", 30, 1, 120),
        ("delay_seconds", 1, 0, 30),
        ("retries", 2, 0, 5),
    ]:
        value = data.get(field, default)
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or not lower <= value <= upper):
            raise ValueError(f"Недопустимое значение {field}: диапазон {lower}..{upper}.")
        if field == "retries" and not isinstance(value, int):
            raise ValueError("retries должен быть целым числом.")
        data[field] = value
    return data
