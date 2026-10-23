"""Короткий честно обозначенный пример вывода для демонстрации."""
from datetime import datetime, timezone
from configuration import ROOT
from main import run_batch
from queries import QUERIES

if __name__ == "__main__":
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    run_batch({}, ROOT / "output" / ("preview_" + stamp),
              demo=True, queries=[QUERIES[3], QUERIES[8], QUERIES[10]])
