"""Запуск: python3 main.py --demo или python3 main.py (настоящий API)."""
import argparse
from datetime import datetime, timezone
import logging
from pathlib import Path
import sys
import time

from client import WolframClient, RequestFailure
from configuration import ROOT, load_config
from demo_data import synthetic_response
from processing import extract
from queries import QUERIES
from storage import redact, write_json, write_report


def run_batch(config, folder, demo=False, queries=QUERIES, client=None):
    folder = Path(folder)
    (folder / "raw").mkdir(parents=True, exist_ok=True)
    (folder / "extracted").mkdir(exist_ok=True)
    mode = "demo" if demo else "live"
    print("РЕЖИМ: " + ("ДЕМО / СИНТЕТИЧЕСКИЕ ДАННЫЕ / БЕЗ API" if demo else "LIVE / WOLFRAM API"))
    records = []
    client = client or (None if demo else WolframClient(config))
    for number, (query_id, category, query) in enumerate(queries, 1):
        timestamp = datetime.now(timezone.utc).isoformat()
        logging.info("Запрос %02d/%02d: %s", number, len(queries), query)
        filename = f"{number:02d}_{query_id}.json"
        secret = config.get("appid", "")
        try:
            raw = synthetic_response(query_id, query) if demo else client.query(query)
            raw = redact(raw, secret)
            write_json(folder / "raw" / filename, raw)
            parsed = extract(raw)
        except RequestFailure as error:
            parsed = {"status": "request_error", "message": str(error), "pods": []}
            write_json(folder / "raw" / filename, {
                "_notice": "Транспортная ошибка; корректный JSON-ответ не получен.",
                "message": redact(str(error), secret),
                "response_body": redact(error.raw_body, secret),
            })
        if demo and parsed["status"] == "no_result":
            parsed["message"] = "Демо моделирует отсутствие ответа. Реальный запрос здесь не выполнялся."
        row = {
            "number": number, "id": query_id, "category": category,
            "query": query, "mode": mode, "timestamp_utc": timestamp,
            **parsed,
        }
        row = redact(row, secret)
        records.append(row)
        write_json(folder / "extracted" / filename, row)
        print(f"{number:02d}. {query}\n    [{row['status']}]")
        for pod in row["pods"]:
            print(f"    {pod['title']}: {' | '.join(pod['text'])}")
        if row["message"]:
            print("    " + row["message"])
        logging.info("Результат %02d: %s", number, row["status"])
        if not demo and number < len(queries):
            time.sleep(config["delay_seconds"])
    write_json(folder / "summary.json", records)
    write_report(folder, records, mode)
    ok = sum(row["status"] == "ok" for row in records)
    print(f"\nОбработано: {len(records)}. С текстовым результатом: {ok}.")
    print("Файлы: " + str(folder))
    logging.info("Пакет завершён: %d запросов, %d текстовых результатов", len(records), ok)
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="Тестовые данные без доступа к API")
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    parser.add_argument("--output", type=Path, help="Новая папка результатов (не должна существовать)")
    args = parser.parse_args()
    try:
        config = {} if args.demo else load_config(args.config)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
        mode = "demo" if args.demo else "live"
        folder = args.output or ROOT / "output" / f"{mode}_{stamp}"
        folder.mkdir(parents=True, exist_ok=False)
        logging.basicConfig(
            filename=folder / "run.log", encoding="utf-8", level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s", force=True,
        )
        rows = run_batch(config, folder, args.demo)
        # no_result тоже отражается в статусе запуска: нельзя молча выдать
        # неуспешную интеграцию за полностью успешную.
        return 0 if args.demo or all(r["status"] == "ok" for r in rows) else 1
    except FileExistsError:
        print("Ошибка: папка результатов уже существует. Выберите новую.", file=sys.stderr)
    except (ValueError, OSError) as error:
        print(f"Ошибка: {error}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
