from __future__ import annotations

import csv
import json
import sqlite3
import os
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

BASE = Path(os.environ.get("APP_DIR", "/app" if Path("/app").exists() else Path(__file__).resolve().parent.parent / "environment"))
DATA = BASE / "data"
OUT = BASE / "output"
CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def D(value) -> Decimal:
    return Decimal(str(value))


def q(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def active_months(hire_date: str, termination_date: str | None, year: int = 2026) -> int:
    hire = date.fromisoformat(hire_date)
    end = date.fromisoformat(termination_date) if termination_date else date(year, 12, 31)
    if end.year < year or hire.year > year:
        return 0
    start_month = hire.month if hire.year == year else 1
    end_month = end.month if end.year == year else 12
    return max(0, end_month - start_month + 1)


def progressive(taxable: Decimal, bands: list[tuple[Decimal | None, Decimal]]) -> Decimal:
    taxable = max(ZERO, q(taxable))
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


def load_fx() -> dict[str, dict[str, Decimal]]:
    rates = {}
    with (DATA / "fx_rates.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rates[row["date"]] = {"GBP": D(row["GBP_USD"]), "EUR": D(row["EUR_USD"])}
    return rates


def fx_rate(pay_date: str, currency: str, rates: dict[str, dict[str, Decimal]]) -> Decimal:
    if currency == "USD":
        return Decimal("1.0000")
    current = date.fromisoformat(pay_date)
    while current.isoformat() not in rates:
        current -= timedelta(days=1)
    return rates[current.isoformat()][currency]


def gross_for(record: dict) -> Decimal:
    gross = (
        D(record["base_salary"])
        + D(record["overtime_hours"]) * D(record["overtime_rate"])
        - D(record["unpaid_leave_days"]) * D(record["unpaid_leave_daily_rate"])
        + D(record["performance_bonus"])
        + D(record["prior_period_reversal"])
    )
    return q(gross)


def calculate(record: dict, employee: dict, state: dict[str, Decimal], rates):
    jurisdiction = employee["jurisdiction"]
    currency = employee["currency"]
    gross = gross_for(record)
    prior_gross = state["gross"]
    prior_tax = state["tax"]
    cumulative = q(prior_gross + gross)
    factor = D(active_months(employee["hire_date"], employee.get("termination_date"))) / D(12)

    if jurisdiction == "UK":
        allowance = q(D("37700") * factor)
        total_tax = progressive(cumulative - allowance, [
            (D("30000"), D("0.20")),
            (None, D("0.50")),
        ])
        tax = q(total_tax - prior_tax)

        cap = q(D("50270") * factor)
        within_cap = max(ZERO, min(cumulative, cap) - min(prior_gross, cap))
        above_cap = max(ZERO, gross - within_cap)
        ss = q(within_cap * D("0.08") + above_cap * D("0.02"))

    elif jurisdiction == "DE":
        allowance = q(D("12000") * factor)
        total_tax = progressive(cumulative - allowance, [
            (D("20000"), D("0.20")),
            (None, D("0.30")),
        ])
        tax = q(total_tax - prior_tax)

        cap = q(D("80000") * factor)
        ss_base = max(ZERO, min(gross, cap - prior_gross))
        ss = q(ss_base * D("0.19375"))

    elif jurisdiction == "US":
        allowance = q(D("10000") * factor)
        total_tax = progressive(cumulative - allowance, [
            (D("40000"), D("0.10")),
            (D("100000"), D("0.22")),
            (None, D("0.32")),
        ])
        tax = q(total_tax - prior_tax)

        cap = q(D("168600") * factor)
        ss_base = max(ZERO, min(cumulative, cap) - min(prior_gross, cap))
        ss = q(ss_base * D("0.062"))

    else:
        raise ValueError(f"Unsupported jurisdiction: {jurisdiction}")

    net = q(gross - tax - ss)
    rate = fx_rate(record["pay_date"], currency, rates)
    gross_usd = q(gross * rate)
    tax_usd = q(tax * rate)
    ss_usd = q(ss * rate)
    net_usd = q(gross_usd - tax_usd - ss_usd)

    return gross, tax, ss, net, rate, gross_usd, tax_usd, ss_usd, net_usd


def main() -> None:
    employees = {
        e["employee_id"]: e
        for e in json.loads((DATA / "employees.json").read_text(encoding="utf-8"))
    }
    runs = json.loads((DATA / "payroll_runs.json").read_text(encoding="utf-8"))
    rates = load_fx()

    ordered = sorted(runs, key=lambda r: (r["employee_id"], r["pay_date"], r["pay_period"]))
    states = {employee_id: {"gross": ZERO, "tax": ZERO}
              for employee_id in employees}

    OUT.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATA / "payroll.db")
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM processed_payroll_ledger")

        for record in ordered:
            employee = employees[record["employee_id"]]
            values = calculate(record, employee, states[record["employee_id"]], rates)
            gross, tax, ss, net, rate, gross_usd, tax_usd, ss_usd, net_usd = values
            state = states[record["employee_id"]]
            state["gross"] = q(state["gross"] + gross)
            state["tax"] = q(state["tax"] + tax)

            currency = employee["currency"]
            gbp_values = (str(gross), str(tax), str(ss)) if currency == "GBP" else (None, None, None)
            eur_values = (str(gross), str(tax), str(ss)) if currency == "EUR" else (None, None, None)

            cur.execute(
                """
                INSERT INTO processed_payroll_ledger (
                    employee_id, pay_period, jurisdiction, currency,
                    gross_pay_local, tax_withheld_local, social_security_local, net_pay_local,
                    gross_pay_gbp, tax_withheld_gbp, social_security_gbp,
                    gross_pay_eur, tax_withheld_eur, social_security_eur,
                    gross_pay_usd, tax_withheld_usd, social_security_usd, net_pay_usd,
                    fx_rate_used
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["employee_id"], record["pay_period"], employee["jurisdiction"], currency,
                    str(gross), str(tax), str(ss), str(net),
                    *gbp_values, *eur_values,
                    str(gross_usd), str(tax_usd), str(ss_usd), str(net_usd), str(rate),
                ),
            )

        conn.commit()
        totals = cur.execute(
            """
            SELECT COUNT(*), SUM(gross_pay_usd), SUM(net_pay_usd),
                   SUM(tax_withheld_usd), SUM(social_security_usd)
            FROM processed_payroll_ledger
            """
        ).fetchone()
    finally:
        conn.close()

    summary = {
        "total_records_processed": len(runs),
        "reconciled_records": int(totals[0]),
        "total_gross_pay_usd": str(q(D(totals[1]))),
        "total_net_pay_usd": str(q(D(totals[2]))),
        "total_tax_withheld_usd": str(q(D(totals[3]))),
        "total_social_security_usd": str(q(D(totals[4]))),
    }
    (OUT / "payroll_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    with (OUT / "tax_discrepancies.csv").open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerow(
            ["employee_id", "pay_period", "jurisdiction", "error_code", "variance_usd"]
        )


if __name__ == "__main__":
    main()
