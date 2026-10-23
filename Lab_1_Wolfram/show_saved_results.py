"""Просмотр настоящих сохранённых ответов, БЕЗ повторных сетевых запросов."""
import json
from pathlib import Path


def main():
    path = Path(__file__).resolve().parent / "verified_live" / "summary.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    print("WOLFRAM ALPHA / СОХРАНЁННЫЕ LIVE-ОТВЕТЫ")
    print("Это просмотр JSON после настоящего запуска, не новый запрос.")
    print("Дата UTC:", rows[0]["timestamp_utc"].split("T")[0])
    print()
    for row in rows:
        print(f"{row['number']:02d}. [{row['status']}] {row['query']}")
    print()
    ok = sum(row["status"] == "ok" for row in rows)
    print(f"ИТОГО: {ok}/{len(rows)} с текстовыми результатами.")
    print("Полные ответы: verified_live/raw")
    print("Извлечённые ответы: verified_live/extracted")
    print("Отчёт: verified_live/report.md")


if __name__ == "__main__":
    main()
