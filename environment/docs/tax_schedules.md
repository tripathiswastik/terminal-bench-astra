### 2026 Payroll Tax Schedules
These deterministic schedules specify statutory tax and contribution rules for the 2026 tax year. All rates are decimal percentages.
## UK
- Annual personal allowance: GBP 37,700.00; prorate by active months.
- Progressive income tax: 20% on taxable cumulative gross through GBP 30,000.00; 50% above GBP 30,000.00.
- National Insurance: annual contribution ceiling GBP 50,270.00; prorate by active months. Contribution is 8% on the portion of cumulative YTD gross within the ceiling and 2% on the portion above the ceiling. The current-period contribution is the incremental contribution attributable to the current period.

## Germany
- Annual tax allowance: EUR 12,000.00; prorate by active months.
- Progressive income tax: 20% on taxable cumulative gross through EUR 20,000.00; 30% above EUR 20,000.00.
- Employee social security rate: 19.375% of current gross, subject to an annual ceiling of EUR 80,000.00 prorated by active months. The current-period contribution is limited by remaining cumulative ceiling.

## US
- Federal annual allowance: USD 10,000.00; prorate by active months.
- Progressive income tax: 10% on taxable cumulative gross through USD 40,000.00; 22% from USD 40,000.01 through USD 100,000.00; 32% above USD 100,000.00.
- OASDI employee rate: 6.2%, with an annual wage cap of USD 168,600.00 prorated by active months. The current-period contribution is limited by remaining cumulative cap.

For all jurisdictions, current-period tax equals progressive tax computed on cumulative YTD gross after the prorated allowance minus cumulative tax already withheld in earlier settled payroll records. A valid current-period tax may be negative after a large reversal.

All local monetary intermediates and final USD outputs are quantized to cents using ROUND_HALF_UP.
