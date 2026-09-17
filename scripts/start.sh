#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "${BASH_SOURCE[0]%/*}/.." && pwd)"
if [[ -f "$project_root/.venv/Scripts/python.exe" ]]; then
    exec "$project_root/.venv/Scripts/python.exe" "$project_root/scripts/start.py"
elif command -v py >/dev/null 2>&1; then
    exec py -3 "$project_root/scripts/start.py"
elif command -v python >/dev/null 2>&1; then
    exec python "$project_root/scripts/start.py"
else
    echo "Instala Python 3.11 o superior para Windows y vuelve a ejecutar este script." >&2
    exit 1
fi
