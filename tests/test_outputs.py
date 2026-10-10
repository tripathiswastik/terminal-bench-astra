import csv
import json
import os
import sqlite3
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

BASE = Path(os.environ.get("APP_DIR", "/app" if Path("/app").exists() else Path(__file__).resolve().parent.parent / "environment"))
TESTS_DIR = Path(os.environ.get("TESTS_DIR", "/tests" if Path("/tests").exists() else Path(__file__).resolve().parent))
SUMMARY = BASE / "output" / "payroll_summary.json"
CSV_OUT = BASE / "output" / "tax_discrepancies.csv"
DB = BASE / "data" / "payroll.db"
EXPECTED_SUMMARY = TESTS_DIR / "expected_payroll_summary.json"
EXPECTED_LEDGER = TESTS_DIR / "expected_payroll_ledger.json"
Q = Decimal("0.01")
KEYS = [
    "employee_id", "pay_period", "jurisdiction", "currency",
    "gross_pay_local", "tax_withheld_local", "social_security_local",
    "net_pay_local", "gross_pay_usd", "tax_withheld_usd",
    "social_security_usd", "net_pay_usd", "fx_rate_used",
]


def money(v):
    return Decimal(str(v)).quantize(Q, rounding=ROUND_HALF_UP)


def rows():
    con = sqlite3.connect(DB)
    data = con.execute(
        "SELECT " + ",".join(KEYS)
        + " FROM processed_payroll_ledger ORDER BY employee_id,pay_period"
    ).fetchall()
    con.close()
    return [dict(zip(KEYS, row)) for row in data]


def test_artifacts_and_summary():
    assert SUMMARY.exists() and CSV_OUT.exists() and DB.exists()
    summary = json.loads(SUMMARY.read_text())
    expected = json.loads(EXPECTED_SUMMARY.read_text())
    assert summary == expected
    with CSV_OUT.open(encoding="utf-8") as handle:
        assert next(csv.reader(handle)) == [
            "employee_id", "pay_period", "jurisdiction", "error_code", "variance_usd"
        ]

    con = sqlite3.connect(DB)
    count, gross, net, tax, ss = con.execute(
        "SELECT COUNT(*),SUM(gross_pay_usd),SUM(net_pay_usd),"
        "SUM(tax_withheld_usd),SUM(social_security_usd) "
        "FROM processed_payroll_ledger"
    ).fetchone()
    con.close()
    assert count == 24
    assert summary["reconciled_records"] == count
    assert money(summary["total_gross_pay_usd"]) == money(gross)
    assert money(summary["total_net_pay_usd"]) == money(net)
    assert money(summary["total_tax_withheld_usd"]) == money(tax)
    assert money(summary["total_social_security_usd"]) == money(ss)


def test_complete_ledger_ground_truth_and_primary_key():
    actual = rows()
    expected = json.loads(EXPECTED_LEDGER.read_text())
    assert actual == expected

    con = sqlite3.connect(DB)
    info = con.execute("PRAGMA table_info(processed_payroll_ledger)").fetchall()
    keys = [row[1] for row in info if row[5]]
    dupes = con.execute(
        "SELECT employee_id,pay_period,COUNT(*) "
        "FROM processed_payroll_ledger "
        "GROUP BY employee_id,pay_period HAVING COUNT(*) > 1"
    ).fetchall()
    con.close()
    assert keys == ["employee_id", "pay_period"]
    assert not dupes


def test_stateful_multi_period_cases():
    by_id = {(r["employee_id"], r["pay_period"]): r for r in rows()}

    # UK: YTD tax plus a ceiling crossing in the third period.
    uk = by_id[("EMP-8042", "2026-10")]
    assert money(uk["gross_pay_local"]) == Decimal("23963.45")
    assert money(uk["tax_withheld_local"]) == Decimal("4792.69")
    assert money(uk["social_security_local"]) == Decimal("644.87")

    # UK: ceiling was crossed in the previous period; October has only the
    # remaining 2% contribution.
    uk_cap = by_id[("EMP-1102", "2026-10")]
    assert money(uk_cap["social_security_local"]) == Decimal("1088.20")

    # Germany: prorated allowance/cap and a cap that is consumed across periods.
    de_joiner = by_id[("EMP-2197", "2026-11")]
    assert money(de_joiner["tax_withheld_local"]) == Decimal("1600.00")
    assert money(de_joiner["social_security_local"]) == Decimal("1453.13")

    de_cap = by_id[("EMP-3304", "2026-10")]
    assert money(de_cap["social_security_local"]) == Decimal("4843.75")

    # US: the reversal reduces cumulative gross below a prior tax liability,
    # producing a legitimate negative current-period tax and zero OASDI.
    us_reversal = by_id[("EMP-7311", "2026-10")]
    assert money(us_reversal["gross_pay_local"]) == Decimal("-18000.00")
    assert money(us_reversal["tax_withheld_local"]) == Decimal("-1800.00")
    assert money(us_reversal["social_security_local"]) == Decimal("0.00")

    # US: OASDI cap is crossed only after the first two periods.
    us_cap = by_id[("EMP-5506", "2026-10")]
    assert money(us_cap["social_security_local"]) == Decimal("3013.20")


def test_fx_inheritance_and_rounding_order():
    by_id = {(r["employee_id"], r["pay_period"]): r for r in rows()}

    # 2026-01-02 has no supplied rate; lookup must cross the year boundary.
    jan = by_id[("EMP-7744", "2026-01")]
    assert Decimal(str(jan["fx_rate_used"])) == Decimal("1.1650")

    # 2026-11-01 has no rate; 2026-10-30 is the nearest prior supplied rate.
    nov = by_id[("EMP-2197", "2026-11")]
    assert Decimal(str(nov["fx_rate_used"])) == Decimal("1.0820")

    # Unpaid leave uses a half-up local quantization before downstream math.
    uk = by_id[("EMP-8042", "2026-10")]
    assert money(uk["gross_pay_local"]) == Decimal("23963.45")
    assert money(uk["gross_pay_usd"]) == Decimal("31253.13")


def test_accounting_invariants_and_precision():
    for row in rows():
        local_net = (
            Decimal(str(row["gross_pay_local"]))
            - Decimal(str(row["tax_withheld_local"]))
            - Decimal(str(row["social_security_local"]))
        )
        usd_net = (
            Decimal(str(row["gross_pay_usd"]))
            - Decimal(str(row["tax_withheld_usd"]))
            - Decimal(str(row["social_security_usd"]))
        )
        assert Decimal(str(row["net_pay_local"])) == local_net
        assert Decimal(str(row["net_pay_usd"])) == usd_net
        for key, value in row.items():
            if key.endswith(("_local", "_usd")):
                assert money(value) == Decimal(str(value))


def test_each_employee_has_three_settled_periods():
    con = sqlite3.connect(DB)
    counts = con.execute(
        "SELECT employee_id,COUNT(*) FROM processed_payroll_ledger "
        "GROUP BY employee_id ORDER BY employee_id"
    ).fetchall()
    con.close()
    assert len(counts) == 8
    assert all(count == 3 for _, count in counts)


if __name__ == "__main__":
    test_functions = [f for name, f in sorted(globals().items()) if name.startswith("test_") and callable(f)]
    for fn in test_functions:
        print(f"  [RUN] {fn.__name__}...")
        fn()
        print(f"  [PASS] {fn.__name__}")
    print("\nAll verifier tests passed successfully (24/24 records reconciled)!")
