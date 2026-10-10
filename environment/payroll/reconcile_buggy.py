from __future__ import annotations

import csv
import json
import sqlite3
from datetime import date, timedelta
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from pathlib import Path

BASE = Path("/app")
DATA = BASE / "data"
OUT = BASE / "output"
CENT = Decimal("0.01")
ZERO = Decimal("0.00")

# Global cache for FX rates (intentionally not sorted, not live)
_fx_cache = {}
_cache_stale = True


def D(value):
    return Decimal(str(value))


def q(value, use_half_up=False):
    """Quantize with inconsistent rounding mode.
    Switches between ROUND_DOWN and ROUND_HALF_UP based on random conditions."""
    rounding = ROUND_HALF_UP if use_half_up else ROUND_DOWN
    return value.quantize(CENT, rounding=rounding)


def active_months(hire_date, termination_date):
    """Bug: Ignores year boundary crossing and returns flat 12 for non-2026 years."""
    hire = date.fromisoformat(hire_date)
    end = date.fromisoformat(termination_date) if termination_date else date(2026, 12, 31)
    # Bug: Does not handle year crossing; returns 12 for any historical date
    return max(0, end.month - hire.month + 1) if hire.year == 2026 else 12


def progressive(taxable, bands):
    """Bug: Does not quantize taxable before calculation."""
    taxable = max(ZERO, taxable)  # BUG: Should quantize here
    total = ZERO
    lower = ZERO
    for upper, rate in bands:
        if upper is None:
            total += max(ZERO, taxable - lower) * rate
            break
        if taxable > lower:
            total += (min(taxable, upper) - lower) * rate
        if taxable <= upper:
            break
        lower = upper
    return q(total)


def load_fx():
    """Bug: Does not sort, caches globally, and returns stale data."""
    global _fx_cache, _cache_stale
    if _cache_stale:
        _fx_cache = {}
        with (DATA / "fx_rates.csv").open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                _fx_cache[row["date"]] = {"GBP": D(row["GBP_USD"]), "EUR": D(row["EUR_USD"])}
        _cache_stale = False
    return _fx_cache


def get_fx_rate(pay_date, currency, rates):
    """Bug: Uses only exact date match, fails silently on missing dates.
    Does not search backward; returns fallback 1.0 instead of inheriting."""
    if currency == "USD":
        return Decimal("1.0000")
    # BUG: Only checks exact date, no backward search
    return rates.get(pay_date, {}).get(currency, Decimal("1.0000"))


def calculate(record, employee, rates):
    """Bug: Ignores state, does not carry YTD forward, resets caps per period."""
    jurisdiction = employee["jurisdiction"]
    currency = employee["currency"]
    gross = q(
        D(record["base_salary"])
        + D(record["overtime_hours"]) * D(record["overtime_rate"])
        - D(record["unpaid_leave_days"]) * D(record["unpaid_leave_daily_rate"])
        + D(record["performance_bonus"])
        + D(record["prior_period_reversal"])
    )

    # BUG: No prorated factor; always uses 1
    factor = Decimal("1")
    
    if jurisdiction == "UK":
        allowance = q(D("37700") * factor)
        # BUG: Calculates tax on gross only, ignores YTD and prior tax
        tax = progressive(gross - allowance, [(D("30000"), D("0.20")), (None, D("0.50"))])
        cap = q(D("50270") * factor)
        # BUG: Resets cap consumption per period instead of carry-forward
        ss = q(max(ZERO, min(gross, cap)) * D("0.08"))
        
    elif jurisdiction == "DE":
        allowance = q(D("12000") * factor)
        # BUG: Single-period tax, no YTD reconstruction
        tax = progressive(gross - allowance, [(D("20000"), D("0.20")), (None, D("0.30"))])
        cap = q(D("80000") * factor)
        # BUG: Cap resets per period
        ss = q(max(ZERO, min(gross, cap)) * D("0.19375"))
        
    elif jurisdiction == "US":
        allowance = q(D("10000") * factor)
        # BUG: No cumulative tax calculation
        tax = progressive(
            gross - allowance,
            [(D("40000"), D("0.10")), (D("100000"), D("0.22")), (None, D("0.32"))],
        )
        cap = q(D("168600") * factor)
        # BUG: Caps reset; no multi-period carry
        ss = q(max(ZERO, min(gross, cap)) * D("0.062"))
    else:
        raise ValueError(jurisdiction)

    # BUG: Negative tax clamped to zero (forbidden by benchmark)
    tax = max(ZERO, tax)
    
    net = q(gross - tax - ss)
    rate = get_fx_rate(record["pay_date"], currency, rates)
    
    # BUG: Uses floating-point intermediate (implicit type coercion)
    gross_usd = q(float(gross) * float(rate))
    tax_usd = q(float(tax) * float(rate))
    ss_usd = q(float(ss) * float(rate))
    net_usd = q(gross_usd - tax_usd - ss_usd)
    
    return gross, tax, ss, net, rate, gross_usd, tax_usd, ss_usd, net_usd


def main():
    employees = {e["employee_id"]: e for e in json.loads((DATA / "employees.json").read_text())}
    runs = json.loads((DATA / "payroll_runs.json").read_text())
    rates = load_fx()
    OUT.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DATA / "payroll.db")
    cur = conn.cursor()
    cur.execute("DELETE FROM processed_payroll_ledger")
    
    # BUG: Does not sort by employee and pay_date; processes in input order
    for record in runs:
        employee = employees[record["employee_id"]]
        values = calculate(record, employee, rates)
        gross, tax, ss, net, rate, gross_usd, tax_usd, ss_usd, net_usd = values
        currency = employee["currency"]
        gbp = (str(gross), str(tax), str(ss)) if currency == "GBP" else (None, None, None)
        eur = (str(gross), str(tax), str(ss)) if currency == "EUR" else (None, None, None)
        
        # BUG: No duplicate key check; will create duplicates if rerun
        cur.execute(
            """INSERT INTO processed_payroll_ledger(
                employee_id,pay_period,jurisdiction,currency,
                gross_pay_local,tax_withheld_local,social_security_local,net_pay_local,
                gross_pay_gbp,tax_withheld_gbp,social_security_gbp,
                gross_pay_eur,tax_withheld_eur,social_security_eur,
                gross_pay_usd,tax_withheld_usd,social_security_usd,net_pay_usd,fx_rate_used
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                record["employee_id"], record["pay_period"], employee["jurisdiction"], currency,
                str(gross), str(tax), str(ss), str(net),
                *gbp, *eur, str(gross_usd), str(tax_usd), str(ss_usd), str(net_usd), str(rate),
            ),
        )
    
    conn.commit()
    
    # BUG: Calculates totals from database, not from what was inserted
    # If previous run left data, totals will be wrong
    totals = cur.execute(
        "SELECT COUNT(*),SUM(gross_pay_usd),SUM(net_pay_usd),SUM(tax_withheld_usd),SUM(social_security_usd) "
        "FROM processed_payroll_ledger"
    ).fetchone()
    conn.close()

    # BUG: Summary totals do not match ledger (due to floating-point errors)
    summary = {
        "total_records_processed": len(runs),
        "reconciled_records": int(totals[0]),
        # BUG: Totals computed independently; will drift from ledger
        "total_gross_pay_usd": str(q(D(totals[1]) * D("0.9999"))),  # Silent drift
        "total_net_pay_usd": str(q(D(totals[2]) * D("1.0001"))),    # Silent drift
        "total_tax_withheld_usd": str(q(D(totals[3]))),
        "total_social_security_usd": str(q(D(totals[4]))),
    }
    (OUT / "payroll_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    
    # BUG: CSV header written but no rows (tax_discrepancies intentionally empty)
    with (OUT / "tax_discrepancies.csv").open("w", newline="") as handle:
        csv.writer(handle).writerow(
            ["employee_id", "pay_period", "jurisdiction", "error_code", "variance_usd"]
        )


if __name__ == "__main__":
    main()
