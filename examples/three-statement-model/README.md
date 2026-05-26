# Three-Statement Model Example

*Run from the repo root: `uv run python examples/three-statement-model/main.py`. Code: [main.py](./main.py).*

This example builds a simple financial model with connected income, cash flow, and balance sheet statements. Income and cash flow line items are modeled as monthly `SpanSeries`. Balance sheet accounts are modeled as `PointSeries`.

## Statement structure

```text
Financial model
├── Income statement
│   └── Net income
│       ├── EBIT
│       │   ├── Gross profit
│       │   │   ├── Revenue
│       │   │   └── Cost of revenue
│       │   ├── Operating expenses
│       │   └── Depreciation
│       └── Income tax
├── Cash flow statement
│   └── Total cash flow
│       ├── Operating cash flow
│       │   ├── Net income
│       │   └── Depreciation add back
│       ├── Capital expenditures
│       └── Cash flow from financing
└── Balance sheet
    ├── Total assets
    │   ├── Cash
    │   └── PPE net
    ├── Total equity and liabilities
    │   ├── Common stock
    │   └── Retained earnings
    └── Balance sheet check
```

## Line assumtpins and projections

| Line Item | Logic |
| --- | --- |
| **Revenue** | Starts at $1,000/month, grows 20% annually using `1 + r * Actual/360` each monthly period. |
| **Cost of revenue** | Revenue x -0.30. |
| **Gross profit** | Revenue + cost of revenue. |
| **Operating expenses** | Periodic -$200/month via `span.periodic`. |
| **Depreciation** | Beginning-of-period PPE net x `-10% / 12`. |
| **EBIT** | Gross profit + operating expenses + depreciation. |
| **Income tax** | EBIT x -0.20. |
| **Net income** | EBIT + income tax. |
| **Depreciation add back** | Depreciation x -1. |
| **Operating cash flow** | Net income + depreciation add back. |
| **Capital expenditures** | Revenue x -0.05. |
| **Cash flow from financing** | Periodic $0 via `span.periodic`. |
| **Total cash flow** | Operating cash flow + capital expenditures + cash flow from financing. |
| **Cash** | Starts at $1,000 and accumulates total cash flow. |
| **PPE net** | Starts at $10,000, increases by capital expenditures, and decreases by depreciation. |
| **Common stock** | Constant $5,000. |
| **Retained earnings** | Starts at $6,000 and accumulates net income. |
| **Balance sheet check** | Total assets - total equity and liabilities. |

The balance sheet check remains zero because cash absorbs operating, investing, and financing cash flow while retained earnings accumulates net income.

## Output

```txt
Start                                       2025-12-31  2026-01-31  2026-02-28  2026-03-31  2026-04-30  2026-05-31
End                             2025-12-31  2026-01-31  2026-02-28  2026-03-31  2026-04-30  2026-05-31  2026-06-30

        Revenue                               1,000.00    1,015.56    1,033.05    1,050.26    1,068.35    1,086.16
        Cost of revenue                        -300.00     -304.67     -309.91     -315.08     -320.51     -325.85
------------------------------------------------------------------------------------------------------------------
      Gross profit                              700.00      710.89      723.13      735.18      747.85      760.31
      Operating expenses                       -200.00     -200.00     -200.00     -200.00     -200.00     -200.00
      Depreciation                              -83.33      -83.06      -82.79      -82.53      -82.28      -82.04
------------------------------------------------------------------------------------------------------------------
    EBIT                                        416.67      427.83      440.35      452.66      465.57      478.27
    Income tax                                  -83.33      -85.57      -88.07      -90.53      -93.11      -95.65
------------------------------------------------------------------------------------------------------------------
  Net income                                    333.33      342.27      352.28      362.13      372.45      382.62


      Net income                                333.33      342.27      352.28      362.13      372.45      382.62
      Depreciation add back                      83.33       83.06       82.79       82.53       82.28       82.04
------------------------------------------------------------------------------------------------------------------
    Operating cash flow                         416.67      425.32      435.06      444.65      454.73      464.66
    Capital expenditures                        -50.00      -50.78      -51.65      -52.51      -53.42      -54.31
    Cash flow from financing                      0.00        0.00        0.00        0.00        0.00        0.00
------------------------------------------------------------------------------------------------------------------
  Total cash flow                               366.67      374.54      383.41      392.14      401.31      410.35


    Cash                          1,000.00    1,366.67    1,741.21    2,124.62    2,516.76    2,918.08    3,328.42
    PPE net                      10,000.00    9,966.67    9,934.39    9,903.25    9,873.24    9,844.38    9,816.65
------------------------------------------------------------------------------------------------------------------
  Total assets                   11,000.00   11,333.33   11,675.60   12,027.88   12,390.00   12,762.46   13,145.08
    Common stock                  5,000.00    5,000.00    5,000.00    5,000.00    5,000.00    5,000.00    5,000.00
    Retained earnings             6,000.00    6,333.33    6,675.60    7,027.88    7,390.00    7,762.46    8,145.08
------------------------------------------------------------------------------------------------------------------
  Total equity and liabilities   11,000.00   11,333.33   11,675.60   12,027.88   12,390.00   12,762.46   13,145.08
  Balance sheet check                 0.00        0.00        0.00        0.00        0.00        0.00        0.00
```
