# 🌐 Terminal-Bench Astra: Multi-Region Payroll Reconciliation Engine

[![Task Benchmark](https://img.shields.io/badge/Benchmark-Terminal--Bench-blue.svg)](https://github.com/tripathiswastik/terminal-bench-astra)
[![Category](https://img.shields.io/badge/Category-Operations%20%7C%20Financial--Systems-green.svg)](https://github.com/tripathiswastik/terminal-bench-astra)
[![Language](https://img.shields.io/badge/Python-3.11+-yellow.svg)](https://www.python.org/)
[![Database](https://img.shields.io/badge/SQLite-ACID%20Ledger-lightgrey.svg)](https://www.sqlite.org/)
[![Author](https://img.shields.io/badge/Author-Swastik%20Tripathi-purple.svg)](https://github.com/tripathiswastik)

An enterprise-grade, stateful payroll reconciliation evaluation benchmark designed for autonomous AI coding agents and financial systems engineers.

---

## 📌 Overview

This benchmark evaluates autonomous agents on stateful multi-jurisdiction payroll reconciliation across **United States (US)**, **United Kingdom (UK)**, and **Germany (DE)** statutory payroll rules.

The evaluation fixture consists of **24 monthly payroll records across 8 employee histories** (3 pay periods each), deliberately shuffled in non-chronological order. The engine must reconstruct historical YTD states, handle multi-currency conversions with backward rate inheritance, apply progressive tax bands, and maintain accounting invariants against a central SQLite ledger.

---

## 🏗️ Repository Architecture

```text
.
├── task.toml                  # Benchmark task specification, timeouts, and resource quotas
├── instruction.md             # Candidate prompt / instructions given to the agent
├── rubric.txt                 # Detailed scoring rubric (+32 positive, -30 penalty points)
├── README.md                  # Benchmark documentation & architecture overview
│
├── environment/               # Agent execution sandbox
│   ├── Dockerfile             # Container definition for execution runtime
│   ├── data/
│   │   ├── employees.json     # 8 active employee profiles across US, UK, and DE
│   │   ├── payroll_runs.json  # 24 non-chronological monthly payroll run inputs
│   │   ├── fx_rates.csv       # Unsorted daily FX rates requiring backward inheritance
│   │   └── payroll.db         # Central SQLite database with processed_payroll_ledger
│   ├── docs/
│   │   └── tax_schedules.md   # Official statutory rules, brackets, and contribution caps
│   ├── output/                # Artifact directory for reconciliation reports
│   └── payroll/
│       ├── reconcile.py       # Core reconciliation engine to be repaired
│       └── run.sh             # Benchmark execution entrypoint (<=45s constraint)
│
├── solution/                  # Ground truth reference implementation
│   ├── solve.py               # Deterministic reference solution
│   └── solve.sh               # Execution script for reference solution
│
└── tests/                     # Isolated verifier harness (runs in separate container)
    ├── Dockerfile             # Evaluation test container definition
    ├── requirements.txt       # Verifier dependencies
    ├── test.sh                # Test runner script
    ├── test_outputs.py        # Automated validation suite (checks exact cent-level outputs)
    ├── expected_payroll_ledger.json   # Expected 24-row ledger state
    └── expected_payroll_summary.json  # Expected summary totals and metrics
```

---

## ⚙️ Core Engineering Challenges & Edge Cases

| Challenge | Description |
| :--- | :--- |
| **Chronological Reconstruction** | Records are intentionally shuffled. The agent must group by employee and sort by `pay_date` before deriving cumulative gross or tax liabilities. |
| **Cumulative Progressive Taxation** | Precomputed YTD fields are omitted. Taxes must be calculated progressively on cumulative gross after prorated allowances, subtracting prior withheld tax. |
| **Negative Reversals & Refunds** | Supports negative prior-period gross adjustments. Negative tax variances must be correctly credited as refunds without being clamped to zero. |
| **Inclusive Proration** | Mid-year hires and departures prorate annual personal allowances and contribution caps by active employment calendar months (hire month through termination month, inclusive). |
| **Multi-Period Contribution Ceilings** | Enforces statutory social security thresholds across multi-period histories: <br>• **UK NI:** £50,270 cap (8% below, 2% above)<br>• **Germany:** €80,000 cap (19.375% below, 0% above)<br>• **US OASDI:** $168,600 cap (6.2% below, 0% above) |
| **Calendar-Day FX Inheritance** | Missing dates in `fx_rates.csv` require recursive backward lookup by calendar day until a valid rate is found, including crossing December 31/January 1 year boundaries. |
| **Multi-Stage Decimal Quantization** | Strict monetary precision using `Decimal` and `ROUND_HALF_UP` across multiple intermediate stages. Floating-point arithmetic is strictly penalized. |
| **Idempotency & Accounting Identities** | Multiple runs must be strictly idempotent with no duplicate ledger keys `(employee_id, pay_period)`. Enforces: <br>`net_pay = gross_pay - tax_withheld - social_security` in both local currency and USD. |

---

## 🚀 Running the Benchmark

### 1. Execute the Agent Runner
```bash
cd environment
bash payroll/run.sh
```

### 2. Verify with the Test Suite
The test verifier runs in an isolated container and validates exact cent-level accounting:
```bash
cd tests
pytest test_outputs.py -v
```

---

## 📊 Verification Contract & Expected Artifacts

The reconciliation engine must produce the following deterministic artifacts:

1. **`payroll_summary.json`** (`/app/output/payroll_summary.json`):
   ```json
   {
     "total_records_processed": 24,
     "reconciled_records": 24,
     "total_gross_pay_usd": 403816.63,
     "total_net_pay_usd": 277253.19,
     "total_tax_withheld_usd": 85721.28,
     "total_social_security_usd": 40842.16
   }
   ```
2. **`tax_discrepancies.csv`** (`/app/output/tax_discrepancies.csv`):
   Captures any ledger or tax discrepancies (`employee_id,pay_period,jurisdiction,error_code,variance_usd`).
3. **`payroll.db`** (`/app/data/payroll.db`):
   Central SQLite table `processed_payroll_ledger` updated with all 24 reconciled rows.


---

## 🔍 Code-Level Defect Catalog (`environment/payroll/reconcile.py`)

The starter script embodies nine concrete software defects that AI coding agents must diagnose, refactor, and resolve:

| # | Concrete Code Defect | Flawed Implementation (`reconcile.py`) | Correct Engineering Implementation (`solution/solve.py`) |
| :--- | :--- | :--- | :--- |
| **1** | **Truncation vs Half-Up Rounding** | `value.quantize(CENT, rounding=ROUND_DOWN)` drops partial cents | `value.quantize(CENT, rounding=ROUND_HALF_UP)` enforces statutory rounding |
| **2** | **Missing FX Backward Inheritance** | `rates.get(date, {}).get(cur, Decimal("1.0000"))` falls back to `1.0` | Calendar-day backward search traversing dates and year boundaries |
| **3** | **Unstaged Precision & Drift** | Converts or computes without staged decimal quantization | Strict `Decimal` quantization across all seven distinct accounting stages |
| **4** | **Absence of Stateful YTD State** | `calculate(record, employee, rates)` evaluates records in isolation | `calculate(record, employee, state, rates)` accumulating cumulative gross and withheld tax |
| **5** | **Flawed Active-Month Proration** | `active_months()` returns flat `12` for non-2026 years | `max(0, end_month - start_month + 1)` bounded by hire, departure, and tax year |
| **6** | **Unsorted FX Data Structure** | Loads CSV as an unsorted dictionary without chronological indexing | Chronologically sorted date structure with deterministic lookup |
| **7** | **Non-Idempotent Ledger Deletion** | Unguarded table wipe without upsert or indexed conflict handling | Deterministic single transaction with primary key `(employee_id, pay_period)` integrity |
| **8** | **No Database Transaction Safety** | Unguarded cursor execution without connection management | Structured `try...finally` wrapping with single atomic commit |
| **9** | **Missing Explicit File Encoding** | Relies on OS-default encoding for file read/write | Enforces explicit `encoding="utf-8"` across all JSON and CSV I/O |

---

## 👤 Author & Organization

- **Author:** [Swastik Tripathi](https://github.com/tripathiswastik)
- **Organization:** BizTech Analytics
- **Benchmark Suite:** Terminal-Bench / Astra Evaluator
