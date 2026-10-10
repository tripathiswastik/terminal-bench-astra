#!/bin/bash
set -euo pipefail

if [ -f "/solution/solve.py" ] && [ -d "/app/payroll" ]; then
    cp /solution/solve.py /app/payroll/reconcile.py
fi

python3 /solution/solve.py
