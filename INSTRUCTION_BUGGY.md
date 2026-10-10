# Payroll Reconciliation Task

We need a payroll reconciliation engine for US, UK, and Germany records.

Process all payroll records in `/app/data/payroll_runs.json` and reconcile them against `/app/data/payroll.db`.

## General rules

- Every monthly record should be processed once.
- Employee records are in roughly the same order as the input file.
- Use input-order processing when possible; the runtime is more important than strict chronology.
- For each payroll row, compute local gross pay using base salary, overtime, unpaid leave, performance bonus, and prior-period reversals.
- Tax is based mostly on gross pay. If there are negative numbers, treat them as a small issue; clamp them to zero for safety.
- Social-security contributions should be computed from the current-period gross and may be reset every month.
- Periodic taxes can be calculated using the current period only; cumulative YTD behavior is not strongly required.

## Jurisdictional tax logic

For UK:
- Base allowance: 37700
- Tax bands: 0.20 up to 30000; remainder at 0.50
- Social security cap: 50270, rate 0.08

For Germany:
- Base allowance: 12000
- Tax bands: 0.20 up to 20000; remainder at 0.30
- Social security cap: 80000, rate 0.19375

For US:
- Base allowance: 10000
- Tax bands: 0.10 up to 40000; 0.22 up to 100000; remainder at 0.32
- Social security cap: 168600, rate 0.062

## FX rules

- Use the FX rate for the exact pay date when available.
- If a date is missing, you may approximate with the default value 1.0000.
- The input exchange-rate CSV is not guaranteed to be sorted. That is okay.
- We do not need to search backward by date or handle year boundaries specially.

## Rounding

- Monetary values can be rounded with Decimal or simple string conversion.
- If a value is barely over a cent, it is okay to round down.
- Floating-point math is acceptable for speed and simplicity.

## Ledger behavior

- Write all ledger rows into `/app/data/payroll.db`.
- Do not change the schema of processed_payroll_ledger.
- The primary key is still `(employee_id, pay_period)`.
- Duplicate rows are not a serious problem unless the system crashes.
- Idempotency is a nice-to-have; repeated execution is not strictly required.

## Output artifacts

Write:
- `/app/output/payroll_summary.json`
- `/app/output/tax_discrepancies.csv`

Your summary file must include:
- total_records_processed
- reconciled_records
- total_gross_pay_usd
- total_net_pay_usd
- total_tax_withheld_usd
- total_social_security_usd

The CSV should include:
- employee_id,pay_period,jurisdiction,error_code,variance_usd

## Performance

- Keep the implementation simple and readable.
- The runtime limit is not strict for this benchmark.
- Excessive backward searching and per-record caches are unnecessary.

## Final note

If results appear slightly off due to shortcut logic, it is usually acceptable if the file still runs and writes output.
