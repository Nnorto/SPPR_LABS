#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p results
command -v hdfs >/dev/null || { echo 'Сначала установите и запустите Hadoop/HDFS'; exit 1; }
test -s results/variant11.json || { echo 'Сначала выполните export.py'; exit 1; }
DEST="/user/$(id -un)/patents/variant11/$(date -u +%Y%m%dT%H%M%SZ)"
{
  hadoop version
  hdfs dfsadmin -report
  hdfs dfs -mkdir -p "$DEST"
  hdfs dfs -put results/variant11.json "$DEST/"
  hdfs dfs -ls "$DEST"
  hdfs dfs -cat "$DEST/variant11.json" | shasum -a 256
  shasum -a 256 results/variant11.json
  echo "HDFS destination: $DEST"
} 2>&1 | tee results/hdfs-upload.log
