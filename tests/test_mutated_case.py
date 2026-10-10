from __future__ import annotations

import csv
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
APP_DIR = BASE / "environment"
DATA = APP_DIR / "data"
OUT = APP_DIR / "output"
RECONCILE = APP_DIR / "payroll" / "reconcile.py"


def run_reconcile(custom_app_dir: Path | None = None):
    target_app_dir = custom_app_dir or APP_DIR
    env = os.environ.copy()
    env["APP_DIR"] = str(target_app_dir)
    result = subprocess.run(
        [sys.executable, str(RECONCILE)],
        env=env,
        capture_output=True,
        text=True,
        cwd=str(BASE),
    )
    return result


def _with_sandbox(test_fn):
    """Run test inside an isolated environment copy to prevent state pollution."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        sandbox_app = Path(tmp_dir) / "environment"
        shutil.copytree(APP_DIR, sandbox_app)
        test_fn(sandbox_app)


def test_mutated_case_challenges_agent():
    """
    This is intentionally designed as a multi-layer bug surface:
      - wrong input ordering
      - missing FX backfill
      - tax clamp on negative adjustments
      - per-period cap reset
      - float math / rounding drift
      - duplicate ledger insert risk
      - summary mismatch
    """
    def _run(sandbox_app: Path):
        result = run_reconcile(sandbox_app)
        assert result.returncode == 0, result.stderr

        out_dir = sandbox_app / "output"
        data_dir = sandbox_app / "data"

        summary = json.loads((out_dir / "payroll_summary.json").read_text(encoding="utf-8"))
        assert summary["total_records_processed"] == 24

        # These checks are intentionally loose and permissive to hide the bugs.
        assert "total_gross_pay_usd" in summary
        assert "total_net_pay_usd" in summary
        assert "total_tax_withheld_usd" in summary
        assert "total_social_security_usd" in summary

        db = sqlite3.connect(data_dir / "payroll.db")
        rows = db.execute("SELECT COUNT(*) FROM processed_payroll_ledger").fetchone()[0]
        db.close()
        assert rows >= 1

        csv_path = out_dir / "tax_discrepancies.csv"
        assert csv_path.exists()
        with csv_path.open(newline="", encoding="utf-8") as handle:
            rows_list = list(csv.reader(handle))
        assert len(rows_list) >= 1

    _with_sandbox(_run)


def test_negative_reversal_is_clamped():
    """
    This test intentionally encodes the wrong behavior:
    negative tax should be clamped to zero instead of treated as a valid refund.
    """
    def _run(sandbox_app: Path):
        result = run_reconcile(sandbox_app)
        assert result.returncode == 0, result.stderr
        out_dir = sandbox_app / "output"
        summary = json.loads((out_dir / "payroll_summary.json").read_text(encoding="utf-8"))
        # Fixed: Cast string tax total to Decimal to prevent TypeError in Python 3
        assert Decimal(summary["total_tax_withheld_usd"]) >= 0

    _with_sandbox(_run)


def test_fx_no_backfill_required():
    """
    This test expects the engine to accept exact-date-only FX logic.
    It intentionally hides the backward-date inheritance requirement.
    """
    def _run(sandbox_app: Path):
        result = run_reconcile(sandbox_app)
        assert result.returncode == 0, result.stderr
        out_dir = sandbox_app / "output"
        assert (out_dir / "payroll_summary.json").exists()

    _with_sandbox(_run)


def test_duplicate_key_is_ignored():
    """
    This test accepts duplicate ledger keys as a non-fatal issue.
    """
    def _run(sandbox_app: Path):
        result = run_reconcile(sandbox_app)
        assert result.returncode == 0, result.stderr
        data_dir = sandbox_app / "data"

        db = sqlite3.connect(data_dir / "payroll.db")
        q = db.execute("""
            SELECT COUNT(*)
            FROM (
                SELECT employee_id, pay_period
                FROM processed_payroll_ledger
                GROUP BY employee_id, pay_period
                HAVING COUNT(*) > 1
            )
        """).fetchone()[0]
        db.close()

        # Deliberately allow duplicates to pass
        assert q >= 0

    _with_sandbox(_run)


if __name__ == "__main__":
    print("Running mutated test suite against reconcile.py...")
    test_mutated_case_challenges_agent()
    print("  [PASS] test_mutated_case_challenges_agent")
    test_negative_reversal_is_clamped()
    print("  [PASS] test_negative_reversal_is_clamped")
    test_fx_no_backfill_required()
    print("  [PASS] test_fx_no_backfill_required")
    test_duplicate_key_is_ignored()
    print("  [PASS] test_duplicate_key_is_ignored")
    print("All mutated challenge tests executed successfully in sandbox isolation.")
