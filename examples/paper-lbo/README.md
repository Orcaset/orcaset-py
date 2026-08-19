# Paper LBO

This example builds a model for a simple paper LBO practice case. It highlights sensitivity analysis using custom rules, solving circularity for swept cash, and concise code expression relative to the equivalent Excel build scripts.

The case is from Wharton's career office: [LBO Practice Model](https://careerservices.upenn.edu/resources/lbo-practice-model/).

## Analysis in fewer tokens

The `main.py` file uses significantly fewer tokens than the equivalent build scripts written by Claude Code or ChatGPT to solve this case study in Excel. Orcaset is able to define line items more concisely than Excel build scripts. For example, EBT is define in a single line `ebt = (ebit + interest).named("EBT")`.

This table compares the analysis script in this example using orcaset against Excel scripts from Claude Code and ChatGPT.

| Tool | Tokens | Increase from orcaset |
| --- | ---: | ---: |
| orcaset | 3,322 | 1.0x |
| Claude Code | 7,944 | 2.4x |
| ChatGPT | 9,381 | 2.8x |

*These results are averages over a small number of runs using different Opus and Sol class models. Claude Code was instructed to use the `/xlsx` skill and ChatGPT told to use the `$spreadsheet` plugin. Both were told to use minimal formatting. Resulting scripts were within a relatively tight band of tokens.*

## Reference

[`reference/wharton-lbo-practice-model.xlsx`](reference/wharton-lbo-practice-model.xlsx) — Wharton Career Services LBO practice workbook (blank model, answer key, and notes). Source: [careerservices.upenn.edu](https://careerservices.upenn.edu/resources/lbo-practice-model/).

## Highlights

* **Circularity:** Enabled by passing `seed` and a `distance` function to at least one accessor function that cuts the cycle. No circuit breaker required — orcaset can't get stuck in the same way.
* **Concise:** Significantly more concise than the Python script for building the Excel version.
* **Sensitivity:** Sensitize variables by making them rules set to different values in different contexts.

## Run

This is a standalone uv project with its own library dependencies. orcaset is pinned to `0.8.0` and resolved from the repo checkout.

Requires Python 3.14+.

```sh
cd examples/paper-lbo
uv run python main.py
```

The script prints the following tables.

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


  Debt                      120.00      115.05      108.87      101.28       92.11        0.00        0.00
  Cash sweep                              4.95        6.18        7.59        9.18       10.98
  Balloon payment                         0.00        0.00        0.00        0.00       81.13
  Debt cash flows           120.00       -4.95       -6.18       -7.59       -9.18      -92.11        0.00

  Purchase price           -200.00        0.00        0.00        0.00        0.00        0.00        0.00
  Exit value                  0.00        0.00        0.00        0.00        0.00      322.10        0.00
  Year end fcf payment        0.00        4.95        6.18        7.59        9.18       10.98        0.00
  Debt cash flows           120.00       -4.95       -6.18       -7.59       -9.18      -92.11        0.00
----------------------------------------------------------------------------------------------------------
Levered cash flow           -80.00        0.00        0.00        0.00        0.00      240.98        0.00
MOM: 3.01
IRR: 24.67%

Sources
 Loan: 120.0
 Equity: 80.0
Total sources: 200.0

Uses
 Purchase price: 200.0
Total uses: 200.0

IRR sensitivity
             6%       8%      10%      12%      14%
  3.0x   -1.32%    3.02%    6.99%   10.67%   14.12%
  4.0x    9.92%   13.64%   17.15%   20.50%   23.72%
  5.0x   17.86%   21.34%   24.67%   27.90%   31.02%
  6.0x   24.10%   27.46%   30.72%   33.89%   36.99%
  7.0x   29.29%   32.60%   35.82%   38.98%   42.06%
```