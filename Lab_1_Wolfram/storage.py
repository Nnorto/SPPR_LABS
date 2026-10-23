"""Полные ответы и извлечённые данные сохраняются раздельно."""
import json
from pathlib import Path


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def redact(value, secret):
    """Не допускаем случайного попадания AppID в отчёты или ошибки."""
    if not secret:
        return value
    if isinstance(value, str):
        return value.replace(secret, "[REDACTED_APPID]")
    if isinstance(value, list):
        return [redact(item, secret) for item in value]
    if isinstance(value, dict):
        return {key: redact(item, secret) for key, item in value.items()}
    return value


def write_report(folder, records, mode):
    lines = [
        "# Результаты Wolfram Alpha",
        "",
        f"Режим: {mode}.",
        ("ДЕМО: синтетические тестовые данные, запросы к API не выполнялись."
         if mode == "demo" else "LIVE: ответы получены при сетевом запуске, см. время у каждого запроса."),
        "",
    ]
    for row in records:
        lines.extend([
            f"## {row['number']:02d}. {row['category']}",
            "",
            f"Запрос: `{row['query']}`",
            "",
            f"Время UTC: {row['timestamp_utc']}. Статус: {row['status']}.",
            "",
        ])
        if row["message"]:
            lines.extend([row["message"], ""])
        for pod in row["pods"]:
            lines.extend([f"### {pod['title']}", "", *pod["text"], ""])
    Path(folder, "report.md").write_text("\n".join(lines), encoding="utf-8")
