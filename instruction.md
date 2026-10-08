Repair the multi-region payroll reconciliation engine in `/app/payroll/reconcile.py` so that all monthly employee payouts, progressive tax withholdings, and statutory social security contributions across US, UK, and Germany reconcile accurately against the central ledger at `/app/data/payroll.db`.


1. Process monthly records in `/app/data/payroll_runs.json` against tax schedules in `/app/docs/tax_schedules.md`, daily exchange rates in `/app/data/fx_rates.csv`, and active employee profiles in `/app/data/employees.json`.

2. **Stateful YTD taxation:** `payroll_runs.json` does not contain precomputed YTD fields. For each employee, derive cumulative YTD gross and cumulative tax already withheld from earlier settled payroll records for that employee. Payroll input order is not chronological. Process each employee's records in ascending `pay_date` order before calculating cumulative tax or contribution ceilings.

3. **Current-period tax:** For each payroll record, compute progressive tax on cumulative YTD gross after the employee's prorated annual allowance, then subtract cumulative tax already withheld in earlier settled periods. Current-period tax may be negative when a reversal reduces cumulative tax liability below tax already withheld. Do not clamp a valid negative tax refund to zero.

4. **Prorated allowances & caps:** For mid-year joiners and leavers, statutory annual tax allowances and social-security contribution ceilings must be prorated by active employment months in the tax year. Active employment months are counted as calendar months from the hire month through the termination month (or December for an active employee), inclusive. The number of payroll records is not the month count, and the first payroll date is not the hire month.

5. **Gross adjustments:** Taxable gross incorporates base salary, overtime, performance bonuses, unpaid-leave deductions, and negative prior-period overpayment reversals. Quantize the resulting local gross to 2 decimal places with `ROUND_HALF_UP` before it participates in tax, social-security, or FX calculations.

6. **UK National Insurance:** The prorated annual ceiling is GBP 50,270 × active_months / 12. Across an employee's YTD history, charge 8% on the portion up to the ceiling and 2% on the portion above it. A ceiling crossed in an earlier period remains crossed for later periods.

7. **Germany social security:** The prorated annual ceiling is EUR 80,000 × active_months / 12. Employee social security is 19.375% of the current-period gross until the cumulative ceiling is consumed. A ceiling crossed in an earlier period must reduce or eliminate later-period contribution base.

8. **US OASDI:** The prorated annual wage cap is USD 168,600 × active_months / 12. Employee OASDI is 6.2% of the current-period amount that remains under the cumulative cap. A cap crossed in an earlier period must reduce or eliminate later-period contribution base.

9. **Cross-year FX business-day inheritance:** A date is a valid FX business day only when an entry exists for that date in `fx_rates.csv`. For a missing payroll date, search backward one calendar day at a time until a supplied rate is found, including crossing a year boundary. The FX CSV is not guaranteed to be sorted.

10. **Multi-stage quantization:** Use `Decimal` and `ROUND_HALF_UP` at these exact stages: (a) quantize calculated local gross to 2 decimal places before YTD, tax, social-security, or FX calculations; (b) quantize cumulative YTD gross to 2 decimal places before progressive-tax calculations; (c) quantize total cumulative tax and the resulting current-period tax to 2 decimal places; (d) quantize each social-security contribution to 2 decimal places; (e) quantize local net pay to 2 decimal places; (f) multiply each local gross, tax, social-security, and net amount by the selected FX rate and quantize each resulting USD amount to 2 decimal places; and (g) calculate USD net pay from the already-quantized USD gross, tax, and social-security amounts, then quantize it to 2 decimal places. Do not use binary floating-point arithmetic for monetary values.

**Rounding example:** If an intermediate local calculation is `10.005`, it becomes `10.01` before the next stage. If that resulting amount is converted at `0.8450`, the USD result is `8.46` after final cent quantization. Do not defer the first rounding step until after FX conversion.

11. **Accounting integrity:** For every ledger row, `net_pay_local = gross_pay_local - tax_withheld_local - social_security_local`, and `net_pay_usd = gross_pay_usd - tax_withheld_usd - social_security_usd`.

12. **Artifacts:** Write `/app/output/payroll_summary.json` containing exactly: `total_records_processed`, `reconciled_records`, `total_gross_pay_usd`, `total_net_pay_usd`, `total_tax_withheld_usd`, `total_social_security_usd`. Write `/app/output/tax_discrepancies.csv` with columns `employee_id,pay_period,jurisdiction,error_code,variance_usd`.

13. **Ledger schema and idempotency:** Do not alter the schema or primary key `(employee_id, pay_period)` of `processed_payroll_ledger`. Re-running `/app/payroll/run.sh` must not create duplicate ledger rows and must leave the derived database and output artifacts deterministic.

14. **Execution constraint:** `/app/payroll/run.sh` must complete within 45 seconds.


- `/app/data/payroll_runs.json` — 24 monthly payroll records in deliberately non-chronological input order.
- `/app/data/employees.json` — 8 employee profiles across UK, Germany, and US.
- `/app/data/fx_rates.csv` — unsorted daily FX data with missing payroll dates that require backward inheritance, including a January payroll date that crosses into the prior year's rates.
- `/app/data/payroll.db` — central SQLite database containing `processed_payroll_ledger`.
- `/app/docs/tax_schedules.md` — jurisdictional tax and contribution schedules.
- `/app/output/` — output artifact directory.

The dataset deliberately combines multiple rules on the same employee histories. Do not assume one payroll record is independent of another.

Do not alter the ledger schema or primary key `(employee_id, pay_period)`.

You have 28800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
