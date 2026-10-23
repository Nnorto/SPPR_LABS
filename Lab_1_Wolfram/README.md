# Wolfram Alpha API

Это первая лабораторная: 10 обязательных и 5 дополнительных запросов. Исходный список находится в `queries.py`, пояснения и листинг в `REPORT.md` и `REPORT.docx`.

## Запуск из этой папки

```bash
python3 setup_config.py
python3 main.py
```

`setup_config.py` попросит AppID скрытым вводом и сохранит локальный `config.json`. Не пересылай этот файл и не помещай его в репозиторий.

Для проверки без сети:

```bash
python3 main.py --demo
python3 -m unittest -v
```

## Результаты

Новые запуски попадают в `output/live_...` или `output/demo_...`. Ранее выполненная проверка API находится в `verified_live`: все 15 запросов получили статус `ok`.

```bash
python3 show_saved_results.py
```

Эта команда только читает сохранённые LIVE-результаты. `LIVE_RESULTS.md` содержит основные ответы, `verified_live/report.md` содержит все извлечённые текстовые блоки; `example_demo` содержит только синтетические фикстуры.

## Конфигурация

`config.example.json` показывает структуру настроек. Для Mac используй Python 3.10+; программа требует только стандартную библиотеку.

Подробная установка и устранение ошибок: `START_HERE.md` в корне комплекта. Структура запроса и ответа описана в [официальной документации Wolfram](https://products.wolframalpha.com/api/documentation).
