# Tootsie Roll

This example builds a financial model for Tootsie Roll (TR). It builds connected income, balance sheet, and cash flow statements. The model pulls nine quarters of historical filing data from CSV documents. Statement presentation follows the same format as TR's filings.

The model contains approximately 100 line items plus dynamically generated line items for the detailed depreciation schedule. It is meant to demonstrate how to build models using Ocaset rather than being the basis for actual investment.

## Project layout

```
tr/
├── README.md
├── main.py                      # Prints the three statements and a balance check
├── depreciation_schedule.py     # Prints cohort-level capex and depreciation detail
└── model/
    ├── __init__.py              # Public entry points: statements, Assumptions, ModelContext
    ├── assumptions.py           # Assumption dataclasses and the ModelContext they ride on
    ├── data.py                  # Loads historical filing data from CSV
    ├── income.py                # Income statement line items
    ├── ppe.py                   # Fixed asset schedule: capex and cohort depreciation
    ├── assets.py                # Balance sheet assets
    ├── liabilities.py           # Balance sheet liabilities
    ├── equity.py                # Balance sheet equity
    ├── balance_sheet.py         # Assembles the balance sheet statement
    ├── cash_flow.py             # Cash flow statement line items
    ├── dividends.py             # Dividends and share repurchases
    ├── checks.py                # pytest model invariant checks
    └── data/
        ├── historical-income.csv
        ├── historical-balance-sheet.csv
        └── historical-cash-flow.csv
```

## Run this model

Clone the repo and navigate to this directory (`examples/tr`), then run the `main.py`:

```sh
cd examples/tr
python main.py
```

## Fixed asset schedule

The fixed asset schedule lives in `model/ppe.py`. It projects capital expenditures and builds a cohort-based depreciation schedule from them. Its outputs feed the cash flow statement (`capex`, `depreciation`) and the balance sheet (gross buildings and machinery roll forward with class capex, and accumulated depreciation rolls forward with total depreciation).

TR does not disclose the split of costs between buildings and machinery, nor a runoff schedule for the amounts currently on the balance sheet, so the schedule is built from a small set of assumptions, each anchored to a filed number:

- **Capital expenditures** continue historicals at a flat quarterly amount equal to the average of the last eight historical quarters.
- **Class split.** Capex is allocated between buildings and machinery by each class's share of gross balance growth over the historical window (about 26% buildings). The `building_capex_share` assumption overrides the derived split when set.
- **Existing PPE** runs off as a single combined cohort: the net depreciable base (gross buildings plus machinery less accumulated depreciation) depreciates at the trailing-four-quarter reported run-rate until exhausted. Anchoring to the run-rate keeps projected depreciation continuous with historicals, and using one combined cohort avoids inventing a class split of accumulated depreciation that TR does not disclose.
- **New capex** depreciates in cohorts: each projected quarter of class capex becomes a cohort depreciating straight-line over the class useful life (`buildings_useful_life_years` and `machinery_useful_life_years` assumptions), starting the quarter after the spend.

Total depreciation is reported historicals followed by the sum of the existing-pool runoff and the two classes' cohort totals.

The cohort schedules are exposed as keyed series (`building_depreciation_cohorts` and `machinery_depreciation_cohorts`) and can be queried per cohort. See run the `depreciation_schedule.py` file to see cohort-level detail.

## Verification

The `main.py` file prints confirmation that balance sheet assets equal liabilities plus equity. Additional model tests are included in the `model/checks.py` file. This file uses `pytest` to verify several standard model invariants.

- Balancing BS: Assets equal liabilities plus equity
- Total cash roll forward: Beginning BS cash and restricted cash plus change in cash from the CF statement equals ending cash and restricted cash
- Restricted cash roll forward: Beginning restricted cash plus change in restricted cash equals ending restricted cash
- Equity roll forward: Beginning BS equity plus retained earnings less dividends and share repurchases equals ending equity
