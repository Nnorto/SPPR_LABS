"""Настройка на личном Mac. Не отправляет ключ в сеть."""
import getpass
import json
import os
from configuration import ROOT


def main():
    path = ROOT / "config.json"
    if path.exists():
        print("config.json уже существует. Измените его локально при необходимости.")
        return
    appid = getpass.getpass("Вставьте личный Wolfram AppID (ввод скрыт): ").strip()
    if not appid or appid == "PUT_YOUR_APPID_HERE":
        print("Пустой/шаблонный AppID. Файл не создан.")
        return
    # O_EXCL не позволяет незаметно перезаписать существующий файл.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        json.dump({
            "appid": appid, "timeout_seconds": 30, "retries": 2, "delay_seconds": 1,
        }, output, ensure_ascii=False, indent=2)
    print("config.json создан. Не отправляйте этот файл преподавателю и не публикуйте.")


if __name__ == "__main__":
    main()
