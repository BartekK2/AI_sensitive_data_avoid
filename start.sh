#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if command -v python3 >/dev/null 2>&1; then
  exec python3 start.py "$@"
fi
if command -v python >/dev/null 2>&1; then
  exec python start.py "$@"
fi
echo "Zainstaluj Python 3.10+ i uruchom ponownie:  python start.py" >&2
exit 1
