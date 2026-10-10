# Payroll Reconciliation Task

Repair the multi-region payroll reconciliation engine in `/app/payroll/reconcile.py` so that all monthly employee payouts, progressive tax withholdings, and statutory social security contributions across US, UK, and Germany reconcile accurately against the central ledger at `/app/data/payroll.db`.

## Core Requirements & Specifications

1. **Input Processing:** Process monthly records in `/app/data/payroll_runs.json` against tax schedules in `/app/docs/tax_schedules.md`, daily exchange rates in `/app/data/fx_rates.csv`, and active employee profiles in `/app/data/employees.json`.

2. **Stateful YTD Taxation:** `payroll_runs.json` does not contain precomputed YTD fields. For each employee, derive cumulative YTD gross and cumulative tax already withheld from earlier settled payroll records for that employee. Payroll input order is deliberately non-chronological. Process each employee's records in ascending `pay_date` order before calculating cumulative tax or contribution ceilings.

3. **Current-Period Tax:** For each payroll record, compute progressive tax on cumulative YTD gross after the employee's prorated annual allowance, then subtract cumulative tax already withheld in earlier settled periods. Current-period tax may be negative when a reversal reduces cumulative tax liability below tax already withheld. Do not clamp a valid negative tax refund to zero.

4. **Prorated Allowances & Caps:** For mid-year joiners and leavers, statutory annual tax allowances and social-security contribution ceilings must be prorated by active employment months in the tax year:
   $$\text{factor} = \frac{\text{active\_months}}{12}$$
   Active employment months are counted as calendar months from the hire month through the termination month (or December for an active employee), inclusive. The number of payroll records is not the month count, and the first payroll date is not the hire month.

5. **Gross Adjustments:** Taxable gross incorporates base salary, overtime, performance bonuses, unpaid-leave deductions, and negative prior-period overpayment reversals:
   $$\text{gross} = \text{base\_salary} + (\text{overtime\_hours} \times \text{overtime\_rate}) - (\text{unpaid\_leave\_days} \times \text{unpaid\_leave\_daily\_rate}) + \text{performance\_bonus} + \text{prior\_period\_reversal}$$
   Quantize the resulting local gross to 2 decimal places with `ROUND_HALF_UP` before it participates in tax, social-security, or FX calculations.

## Jurisdictional Tax & Statutory Contribution Schedules

### United Kingdom (UK - GBP)
- **Base Annual Allowance:** GBP 37,700 $\times$ factor
- **Progressive Tax Bands:**
  - 20% on taxable gross up to GBP 30,000
  - 50% on taxable gross above GBP 30,000
- **National Insurance (Social Security):**
  - Prorated annual ceiling: GBP 50,270 $\times$ factor
  - 8% on cumulative YTD gross up to the ceiling
  - 2% on the portion above the ceiling (a ceiling crossed in an earlier period remains crossed for subsequent periods)

### Germany (DE - EUR)
- **Base Annual Allowance:** EUR 12,000 $\times$ factor
- **Progressive Tax Bands:**
  - 20% on taxable gross up to EUR 20,000
  - 30% on taxable gross above EUR 20,000
- **Social Security:**
  - Prorated annual ceiling: EUR 80,000 $\times$ factor
  - 19.375% on current-period gross until the cumulative ceiling is consumed

### United States (US - USD)
- **Base Annual Allowance:** USD 10,000 $\times$ factor
- **Progressive Tax Bands:**
  - 10% on taxable gross up to USD 40,000
  - 22% on taxable gross between USD 40,000 and USD 100,000
  - 32% on taxable gross above USD 100,000
- **Social Security (OASDI):**
  - Prorated annual wage cap: USD 168,600 $\times$ factor
  - 6.2% on eligible gross under the cumulative cap

## FX Business-Day Inheritance & Rounding Rules

1. **Cross-Year FX Inheritance:** A date is a valid FX business day only when an entry exists for that date in `fx_rates.csv`. For a missing payroll date, search backward one calendar day at a time until a supplied rate is found, including crossing a year boundary. If the currency is USD, the rate is exactly `Decimal("1.0000")`. The FX CSV is not guaranteed to be sorted.
2. **Multi-Stage Quantization:** Use `Decimal` and `ROUND_HALF_UP` at these exact stages:
   - Quantize calculated local gross to 2 decimal places.
   - Quantize cumulative YTD gross to 2 decimal places before progressive-tax calculations.
   - Quantize total cumulative tax and resulting current-period tax to 2 decimal places.
   - Quantize each social-security contribution to 2 decimal places.
   - Quantize local net pay to 2 decimal places:
     $$\text{net\_pay\_local} = \text{gross\_pay\_local} - \text{tax\_withheld\_local} - \text{social\_security\_local}$$
   - Multiply each local gross, tax, social-security, and net amount by the FX rate and quantize each resulting USD amount to 2 decimal places.
   - Calculate USD net pay from already-quantized USD components:
     $$\text{net\_pay\_usd} = \text{gross\_pay\_usd} - \text{tax\_withheld\_usd} - \text{social\_security\_usd}$$
   Do not use binary floating-point arithmetic for monetary calculations.
   Do not defer the first rounding step until after FX conversion.

## Output Artifacts & Ledger Invariants

### 1. Database Ledger (`/app/data/payroll.db`)
- Maintain table `processed_payroll_ledger` with primary key `(employee_id, pay_period)`.
- Do not alter the schema or primary key.
- Re-running `/app/payroll/run.sh` must be idempotent and deterministic without duplicate rows.

### 2. Payroll Summary JSON (`/app/output/payroll_summary.json`)
Must contain exactly:
```json
{
  "total_records_processed": 24,
  "reconciled_records": 24,
  "total_gross_pay_usd": "...",
  "total_net_pay_usd": "...",
  "total_tax_withheld_usd": "...",
  "total_social_security_usd": "..."
}
```

### 3. Tax Discrepancies CSV (`/app/output/tax_discrepancies.csv`)
Must contain header:
```csv
employee_id,pay_period,jurisdiction,error_code,variance_usd
```

## Dataset Files

- `/app/data/payroll_runs.json` — 24 monthly payroll records in non-chronological order.
- `/app/data/employees.json` — 8 employee profiles across UK, Germany, and US.
- `/app/data/fx_rates.csv` — unsorted daily exchange rates requiring recursive backward inheritance.
- `/app/data/payroll.db` — central SQLite database.
- `/app/docs/tax_schedules.md` — jurisdictional tax documentation.
- `/app/output/` — output destination directory.

## Constraints

- `/app/payroll/run.sh` must execute within **45 seconds**.
- Time limit: 28,800 seconds.
