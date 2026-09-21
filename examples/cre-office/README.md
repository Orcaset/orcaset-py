# Office acquisition model

This example contains a simple office acquisition model.

[`Real-Estate-Pro-Forma.xlsx`](Real-Estate-Pro-Forma.xlsx) holds the equivalent model spreadsheet model.

The [`assumptions-outline.md`](assumptions-outline.md) file holds the list of assumptions and instructions used to create the Orcaset model originally.

Run the `proforma.py` file to write the operating pro forma to an HTML table or the `performance.py` file to print risk and return metrics like unlevered and levered IRR, debt yield, and DSCR.

## Layout

| File | Role |
| --- | --- |
| [`assumptions-outline.md`](assumptions-outline.md) | Assumptions file used to originally create the model. |
| [`leases.py`](leases.py) | Lease types, rollover costs, and expense reimbursements. |
| [`operating_model.py`](operating_model.py) | Property operations, replacement reserves, debt schedule, and cash-flow lines. |
| [`html_formatter.py`](html_formatter.py) | HTML table renderer for the operating pro forma. |
| [`proforma.py`](proforma.py) | Statement layout for the operating pro forma. |
| [`performance.py`](performance.py) | Investment cash flows, return metrics, sources and uses, and debt coverage. |

## Run

Python 3.14+ and uv are required. There are two output files: `proforma.py` writes an HTML file with the operating pro forma and the `performance.py` file prints performance metrics.

```sh
uv run examples/cre-office/proforma.py
uv run --with numpy-financial examples/cre-office/performance.py
```

Performance file output:

```txt
Unlevered investment performance
Start                                             2026-12-31    2027-12-31    2028-12-31     2029-12-31
End                                 2026-12-31    2027-12-31    2028-12-31    2029-12-31     2030-12-31
  Purchase price                -25,000,000.00
  Buying costs                     -250,000.00
  Initial reserve funding           -62,500.00
  Unlevered property cash flow            0.00  1,746,656.80  1,841,994.05  1,309,355.58   1,511,918.48
  Sale price                                                                              34,561,864.25
  Selling costs                                                                             -518,427.96
-------------------------------------------------------------------------------------------------------
Total unlevered cash flow       -25,312,500.00  1,746,656.80  1,841,994.05  1,309,355.58  35,555,354.77
Unlevered IRR: 13.47%
Total initial investment: 25,312,500.00
Total capital contributed: 25,312,500.00
Total return (cash distributions): 40,453,361.20
MOIC: 1.60x

Levered equity performance
Start                                                 2026-12-31     2027-12-31     2028-12-31      2029-12-31
End                                    2026-12-31     2027-12-31     2028-12-31     2029-12-31      2030-12-31
  Total unlevered cash flow        -25,312,500.00   1,746,656.80   1,841,994.05   1,309,355.58   35,555,354.77
  Debt draw                         15,000,000.00
  Loan issuance fees                  -225,000.00
  Debt service                               0.00  -1,061,905.72  -1,067,155.72  -1,072,563.22   -1,078,132.94
  Senior debt payoff                                                                            -11,371,153.62
  Mezzanine debt payoff                                                                          -2,813,772.02
--------------------------------------------------------------------------------------------------------------
Total levered cash flow to equity  -10,537,500.00     684,751.08     774,838.33     236,792.36   20,292,296.18
Levered IRR: 21.48%
Total initial investment: 10,537,500.00
Total capital contributed: 10,537,500.00
Total return (cash distributions): 21,988,677.96
MOIC: 2.09x

Sources and uses at acquisition
  Acquisition price               25,000,000.00
  Buying costs                       250,000.00
  Loan issuance fees                 225,000.00
  Upfront reserve funding             62,500.00
Total uses                        25,537,500.00
-----------------------------------------------
  Senior debt                     12,500,000.00
  Mezzanine debt                   2,500,000.00
  Operating partner equity         1,053,750.00
  Limited partner equity           9,483,750.00
Total sources                     25,537,500.00

Debt metrics (coverage ratios in x)
Start                                       2026-12-31  2027-12-31  2028-12-31  2029-12-31
End                             2026-12-31  2027-12-31  2028-12-31  2029-12-31  2030-12-31
Debt yield (%)                                   11.64       12.28        8.73       10.40
NOI interest coverage                             2.00        2.12        1.52        1.82
Adjusted NOI interest coverage                    2.00        2.12        1.52        1.76
NOI DSCR                                          1.54        1.61        1.14        1.35
Adjusted NOI DSCR                                 1.54        1.61        1.14        1.30

Going-in cap rate: 6.99%
Gross exit value: 34,561,864.25
Exit value / RSF: 1,382.47
```
