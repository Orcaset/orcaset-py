# Paper LBO

This example implements the Wharton Career Services paper LBO case with pro forma
financials, a circular average-debt interest calculation, sources and uses, returns,
and a two-variable IRR sensitivity.

The model uses `Series.unfold` for recursive operating lines, `Series.of` for finite
date-keyed cash flows, and explicit `period_union` / `date_union` merge policies for
arithmetic. A local `cumulate` helper uses `scan_cells` to create a running debt balance.

The interest lookup supplies `seed=0.0` and `maybe_abs_distance` at the circular ending
debt demand. `Context` uses that cut to solve the fixed point. Sensitivities replace the
NaN

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
IRR sensitivity
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
| [`references/wharton-lbo-practice-model.xlsx`](references/wharton-lbo-practice-model.xlsx) | Original practice workbook. |
| [`references/example-opus-excel-build-script.py`](references/example-opus-excel-build-script.py) | Reference Excel build script. |
| [`references/example-sol-excel-build-script.mjs`](references/example-sol-excel-build-script.mjs) | Reference Excel build script. |
| [`references/automated-excel-agent-example.xlsx`](references/automated-excel-agent-example.xlsx) | Reference agent-built workbook. |
