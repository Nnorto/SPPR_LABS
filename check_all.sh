#!/bin/bash
# Запуск из любой папки: bash /путь/к/labs_mac/check_all.sh
set -euo pipefail
cd "$(dirname "$0")"
echo "Проверка Python:"
python3 --version
(cd Lab_1_Wolfram && python3 -m unittest -v)
if ! command -v swipl >/dev/null 2>&1; then
    echo "SWI-Prolog не найден. Установите его; см. START_HERE.md."
    exit 1
fi
echo "Проверка SWI-Prolog:"
swipl --version
swipl -q -s Lab_2_Weather/tests.pl -g run_tests -t halt
(cd Lab_3_FuzzyWeather && python3 -m unittest -v)
echo "Все 91 локальных тестов пройдены. Доступ к внешним API этим НЕ проверяется."
