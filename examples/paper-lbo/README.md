# Paper LBO

This example builds a simple paper LBO case. It creates a linked three-statement model to highlight two `orcaset` model patterns.

1. Sensitivity analysis using `Cell` rules to hold assumptions that might change.
2. Circular value references resolved using iterative calculations for the debt draws.

## Sensitivity analysis

The script prints IRR sensitivity to exit multiple and revenue growth rate.

Rather than defining the exit multiple and revenue growth rate assumptions as bare floats, the model wraps them in `Cell`s. The `Cell` type is a simple class that lifts a zero-argument function into an unkeyed rule that the effect handlers can evaluate. It is approximately:

```py
class Cell:
    def __init__(self, fn):
        self.fn = fn

    def compute(self):
        return self.fn()
```

When the value from the cell is needed, the inner function is invoked and the value is stored in the context. The cell *object* doesn't change, only its value. This gives the rest of the model a stable object to reference while the underlying value updates.

```py
annual_revenue_growth = Cell("Revenue growth rate", lambda: 0.1)
exit_multiple = Cell("Exit multiple", lambda: 5.0)
```

Evaluating the sensitivity is simply a matter of (nested) iterations over the assumption values, resolving the output in a *fresh* context each time.

```py
# Assumptions
growth_rates = (0.06, 0.08, 0.10, 0.12, 0.14)
exit_multiples = (3.0, 4.0, 5.0, 6.0, 7.0)

table: list[list[str]] = []  # table to collect nested list of results

for multiple in exit_multiples:  # iterate over multiples
    exit_multiple.fn = lambda multiple=multiple: multiple
    row = [f"{multiple:.1f}x".rjust(6)]

    for growth in growth_rates:  # iterate over growth rates
        annual_revenue_growth.fn = lambda growth=growth: growth
        scenario = Context()

        scenario_cashflows: list[float] = []  # collect cash flows for IRR calc
        for day in cf_dates:
            value = scenario.get_at(levered_cash_flow, day)
            if isna(value):
                raise ValueError(f"missing levered cash flow for {day}")
            scenario_cashflows.append(value)
        row.append(f"{float(npf.irr(scenario_cashflows)):.2%}".rjust(8))
    table.append(row)
```

Sensitivity can be three or more levels deep, unlike spreadsheet data tables which are limited to two dimensions.

## Iterative calculations

Debt draws/repayment plug cash flow gap/surplus, creating a circular dependency between the average debt balance (calculated as the average of beginning and ending debt over the period), interest expense, and cash flow. While this is a simple model and it is technically feasible to unwind the circularity, the case explicitly includes circular construction.

Orcaset natively handles cyclic dependencies. The only requirement is to define a seed value and distance function at least once in the cycle.

This model defines the initial seed value and distance function in the `interest` definition, specifically in the getter for ending debt.

```py
@Series.define("Interest", ...)
def interest(period: Period):
    if period.start >= acquisition_date + hold_period:
        return None
    beginning = yield from get_at(debt_before_balloon, period.start)

    # Starting seed and distance function
    ending = yield from get_at(
        debt_before_balloon,
        period.end,
        seed=0.0,
        distance=maybe_abs_distance,
    )
    ...
```

The default context solver converges when the change in value falls below `1e-9` within 1,000 iterations.

See the [iterative-solver](../iterative-solver/) example for additional detail.

## Run

This is a standalone uv project using the repository checkout of orcaset.

```sh
cd examples/paper-lbo
uv run python main.py
```

Output:

```txt
Start                               2022-12-31  2023-12-31  2024-12-31  2025-12-31  2026-12-31  2027-12-31
End                     2022-12-31  2023-12-31  2024-12-31  2025-12-31  2026-12-31  2027-12-31  2028-12-31

  Revenue                               100.00      110.00      121.00      133.10      146.41      161.05
      EBITDA                             40.00       44.00       48.40       53.24       58.56       64.42
      D&A                               -20.00      -20.00      -20.00      -20.00      -20.00      -20.00
----------------------------------------------------------------------------------------------------------
    EBIT                                 20.00       24.00       28.40       33.24       38.56       44.42
    Interest                            -11.75      -11.20      -10.51       -9.67       -8.66
----------------------------------------------------------------------------------------------------------
  EBT                                     8.25       12.80       17.89       23.57       29.90
  Taxes                                  -3.30       -5.12       -7.16       -9.43      -11.96


    EBITDA                               40.00       44.00       48.40       53.24       58.56       64.42
    Taxes                                -3.30       -5.12       -7.16       -9.43      -11.96
    Interest                            -11.75      -11.20      -10.51       -9.67       -8.66
    Capex                               -15.00      -16.50      -18.15      -19.97      -21.96      -24.16
    Change in NWC                        -5.00       -5.00       -5.00       -5.00       -5.00       -5.00
----------------------------------------------------------------------------------------------------------
  FCF                                     4.95        6.18        7.59        9.18       10.98


  Draws                     120.00        0.00        0.00        0.00        0.00        0.00        0.00
  Cash sweep                             -4.95       -6.18       -7.59       -9.18      -10.98
  Debt before balloon       120.00      115.05      108.87      101.28       92.11       81.13       81.13
  Balloon payment             0.00        0.00        0.00        0.00        0.00      -81.13        0.00
  Debt balance              120.00      115.05      108.87      101.28       92.11        0.00        0.00
  Debt cash flows           120.00       -4.95       -6.18       -7.59       -9.18      -92.11        0.00

  Purchase price           -200.00        0.00        0.00        0.00        0.00        0.00        0.00
  Exit value                  0.00        0.00        0.00        0.00        0.00      322.10        0.00
  Year end fcf payment        0.00        4.95        6.18        7.59        9.18       10.98        0.00
  Debt cash flows           120.00       -4.95       -6.18       -7.59       -9.18      -92.11        0.00
----------------------------------------------------------------------------------------------------------
Levered cash flow           -80.00        0.00        0.00        0.00        0.00      240.98        0.00
MOM: 3.01
IRR: 24.67%
```

```txt
Sources
 Loan: 120.0
 Equity: 80.0
Total sources: 200.0

Uses
 Purchase price: 200.0
Total uses: 200.0
```

```txt
IRR sensitivity to exit multiple and revenue growth rate
             6%       8%      10%      12%      14%
  3.0x   -1.32%    3.02%    6.99%   10.67%   14.12%
  4.0x    9.92%   13.64%   17.15%   20.50%   23.72%
  5.0x   17.86%   21.34%   24.67%   27.90%   31.02%
  6.0x   24.10%   27.46%   30.72%   33.89%   36.99%
  7.0x   29.29%   32.60%   35.82%   38.98%   42.06%
```

## References

| File | Role |
| --- | --- |
| [`references/wharton-lbo-practice-model.xlsx`](references/wharton-lbo-practice-model.xlsx) | Original case workbook. |
| [`references/example-opus-excel-build-script.py`](references/example-opus-excel-build-script.py) | Reference Excel build script. |
| [`references/example-sol-excel-build-script.mjs`](references/example-sol-excel-build-script.mjs) | Reference Excel build script. |
| [`references/automated-excel-agent-example.xlsx`](references/automated-excel-agent-example.xlsx) | Reference agent-built workbook showing LibreOffice-Excel compatibility errors. |
