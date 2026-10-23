# Покраска и родители

Решены вводные запросы по покраске и выбранное задание №1 из PDF с примерами. Семейная база содержит 9 фактов отношений и 12 уникальных людей.

Из этой папки:

```bash
swipl -q -s demo.pl -g demo -t halt
swipl -q -s tests.pl -g run_tests -t halt
```

Для ручных запросов:

```bash
swipl -q -s family.pl
```

```prolog
parents_of('Иван', Parents).
all_pairs(Pairs).
grandparent('Илья', Child).
halt.
```

Покраску можно открыть отдельно с `-s painting.pl`. Отчёт и объяснения находятся в `REPORT.md` и `REPORT.docx`.
