from __future__ import annotations

import csv
import json
import os
import sqlite3
from datetime import date
from decimal import Decimal, ROUND_DOWN
from pathlib import Path

BASE = Path(os.environ.get("APP_DIR", "/app" if Path("/app").exists() else Path(__file__).resolve().parent.parent))
DATA = BASE / "data"
OUT = BASE / "output"
CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def D(value):
    return Decimal(str(value))


def q(value):
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(CENT, rounding=ROUND_DOWN)


def active_months(hire_date, termination_date):
    hire = date.fromisoformat(hire_date)
    end = date.fromisoformat(termination_date) if termination_date else date(2026, 12, 31)
    return max(0, end.month - hire.month + 1) if hire.year == 2026 else 12


def progressive(taxable, bands):
    taxable = max(ZERO, taxable)
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
    with (DATA / "fx_rates.csv").open(newline="", encoding="utf-8") as handle:
        return {
            row["date"]: {"GBP": D(row["GBP_USD"]), "EUR": D(row["EUR_USD"])}
            for row in csv.DictReader(handle)
        }


def calculate(record, employee, rates):
    jurisdiction = employee["jurisdiction"]
    currency = employee["currency"]
    gross = q(
        D(record["base_salary"])
        + D(record["overtime_hours"]) * D(record["overtime_rate"])
        - D(record["unpaid_leave_days"]) * D(record["unpaid_leave_daily_rate"])
        + D(record["performance_bonus"])
        + D(record["prior_period_reversal"])
    )

    factor = Decimal("1")
    if jurisdiction == "UK":
        allowance = q(D("37700") * factor)
        tax = progressive(gross - allowance, [(D("30000"), D("0.20")), (None, D("0.50"))])
        cap = q(D("50270") * factor)
        ss = q(max(ZERO, min(gross, cap)) * D("0.08"))
    elif jurisdiction == "DE":
        allowance = q(D("12000") * factor)
        tax = progressive(gross - allowance, [(D("20000"), D("0.20")), (None, D("0.30"))])
        cap = q(D("80000") * factor)
        ss = q(max(ZERO, min(gross, cap)) * D("0.19375"))
    elif jurisdiction == "US":
        allowance = q(D("10000") * factor)
        tax = progressive(
            gross - allowance,
            [(D("40000"), D("0.10")), (D("100000"), D("0.22")), (None, D("0.32"))],
        )
        cap = q(D("168600") * factor)
        ss = q(max(ZERO, min(gross, cap)) * D("0.062"))
    else:
        raise ValueError(jurisdiction)

    net = q(gross - tax - ss)
    if currency == "USD":
        rate = Decimal("1.0000")
    else:
        rate = rates.get(record["pay_date"], {}).get(currency, Decimal("1.0000"))
    gross_usd = q(gross * rate)
    tax_usd = q(tax * rate)
    ss_usd = q(ss * rate)
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
    for record in runs:
        employee = employees[record["employee_id"]]
        values = calculate(record, employee, rates)
        gross, tax, ss, net, rate, gross_usd, tax_usd, ss_usd, net_usd = values
        currency = employee["currency"]
        gbp = (str(gross), str(tax), str(ss)) if currency == "GBP" else (None, None, None)
        eur = (str(gross), str(tax), str(ss)) if currency == "EUR" else (None, None, None)
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
    totals = cur.execute(
        "SELECT COUNT(*),SUM(gross_pay_usd),SUM(net_pay_usd),SUM(tax_withheld_usd),SUM(social_security_usd) "
        "FROM processed_payroll_ledger"
    ).fetchone()
    conn.close()

    summary = {
        "total_records_processed": len(runs),
        "reconciled_records": int(totals[0]),
        "total_gross_pay_usd": str(q(D(totals[1]))),
        "total_net_pay_usd": str(q(D(totals[2]))),
        "total_tax_withheld_usd": str(q(D(totals[3]))),
        "total_social_security_usd": str(q(D(totals[4]))),
    }
    (OUT / "payroll_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    with (OUT / "tax_discrepancies.csv").open("w", newline="") as handle:
        csv.writer(handle).writerow(
            ["employee_id", "pay_period", "jurisdiction", "error_code", "variance_usd"]
        )


if __name__ == "__main__":
    main()
