# Apartment Acquisition Pro Forma

This example builds an acquisition model for Arcadia Gardens, a 76-unit apartment community in Phoenix. It includes an operating pro forma, unlevered and levered returns, sources and uses, and return metrics (IRR, MOIC, DSCR).

The model follows [`arcadia-gardens-outline.md`](arcadia-gardens-outline.md), which is based on the Excel model [here](https://mergersandinquisitions.com/real-estate-financial-modeling/) with minor changes to reserve funding.

## Run the model

This is a standalone uv project. Python 3.14+ is required. `numpy-financial` is used for IRR calculations and is installed automatically.

```sh
cd examples/multifamily
uv run python proforma.py
uv run python performance.py
```

`proforma.py` prints the annual property pro forma. `performance.py` prints sources and uses, debt coverage, and unlevered and levered IRR, MOIC, and related metrics.

## Project layout

| File | Role |
| --- | --- |
| [`arcadia-gardens-outline.md`](arcadia-gardens-outline.md) | Case assumptions and required outputs. |
| [`model.py`](model.py) | Property operations, replacement reserves, debt schedule, and cash-flow lines. |
| [`proforma.py`](proforma.py) | Statement layout for the operating pro forma. |
| [`performance.py`](performance.py) | Investment cash flows, return metrics, sources and uses, and debt coverage. |

## Output

`proforma.py`:

```txt
Start                                                   2016-12-31    2017-12-31    2018-12-31    2019-12-31    2020-12-31    2021-12-31    2022-12-31
End                                       2016-12-31    2017-12-31    2018-12-31    2019-12-31    2020-12-31    2021-12-31    2022-12-31    2023-12-31

  Rent growth                                                               0.04          0.04          0.04          0.03          0.03          0.03
  Pct loss to lease                                          -0.10         -0.07         -0.05         -0.03         -0.01         -0.01         -0.01
  Bad debt and concessions                                   -0.03         -0.03         -0.02         -0.02         -0.01         -0.01         -0.01
  Utility reimbursement percentage                            0.80          0.83          0.86          0.89          0.92          0.95          0.95
  General vacancy                                             0.00         -0.01         -0.02         -0.03         -0.03         -0.03         -0.03
  Operating expense growth                                                  0.03          0.03          0.03          0.03          0.03          0.03
  Sales, marketing, and administrative %                      0.19          0.19          0.19          0.20          0.20          0.20          0.20
  Property tax growth                                                       0.02          0.02          0.02          0.02          0.02          0.02


  Market rent PSF                                            21.33         22.08         22.85         23.65         24.36         25.09         25.85
  Reserve flows                                 0.00     19,000.00    -38,000.00    -20,727.10    -20,761.81          0.00    -15,200.00          0.00
  Replacement reserve balance                            19,000.00        570.00          0.00          0.00     21,384.67     28,210.87     50,897.87

      Interest expense                                                317,687.50    312,905.85    307,885.11    302,613.34    297,077.98          0.00
      Principal payments                                               95,633.06    100,414.71    105,435.44    110,707.22    116,242.58         -0.00
------------------------------------------------------------------------------------------------------------------------------------------------------
    Debt P&I                                                          413,320.56    413,320.56    413,320.56    413,320.56    413,320.56         -0.00
    Loan balance                                      6,353,750.00  6,258,116.94  6,157,702.24  6,052,266.79  5,941,559.58          0.00          0.00



      Market rent                                       929,024.00    961,539.84    995,193.73  1,030,025.52  1,060,926.28  1,092,754.07  1,125,536.69
      Loss to lease                                     -92,902.40    -72,115.49    -49,759.69    -25,750.64    -10,609.26    -10,927.54    -11,255.37
      Bad debt and concessions amount                   -25,083.65    -26,682.73    -18,908.68    -20,085.50    -10,503.17    -10,818.27    -11,142.81
      Annual parking income                              51,528.00     53,331.48     55,198.08     57,130.01     58,843.92     60,609.23     62,427.51
      Utility reimbursements                             62,016.00     66,271.85     70,727.23     75,390.30     80,269.49     85,373.58     87,934.79
------------------------------------------------------------------------------------------------------------------------------------------------------
    Potential Gross Revenue                             924,581.95    982,344.95  1,052,450.68  1,116,709.69  1,178,927.25  1,216,991.08  1,253,500.81
    Vacancy amount                                            0.00     -9,823.45    -21,049.01    -33,501.29    -35,367.82    -36,509.73    -37,605.02
------------------------------------------------------------------------------------------------------------------------------------------------------
  Effective Gross Revenue                               924,581.95    972,521.50  1,031,401.67  1,083,208.40  1,143,559.43  1,180,481.34  1,215,895.78
    Insurance                                            21,774.00     22,427.22     23,100.04     23,793.04     24,506.83     25,242.03     25,999.29
    Utility expense                                      77,520.00     79,845.60     82,240.97     84,708.20     87,249.44     89,866.93     92,562.93
    Replacement reserves                                 19,000.00     19,570.00     20,157.10     20,761.81     21,384.67     22,026.21     22,686.99
    Sales, marketing, and administrative                175,670.57    186,724.13    200,091.92    212,308.85    226,424.77    236,096.27    243,179.16
    Property taxes                                       66,470.00     67,799.40     69,155.39     70,538.50     71,949.27     73,388.25     74,856.02
    Property management fee                              27,737.46     29,175.65     30,942.05     32,496.25     34,306.78     35,414.44     36,476.87
------------------------------------------------------------------------------------------------------------------------------------------------------
  Total operating expenses                              388,172.03    405,541.99    425,687.47    444,606.64    465,821.76    482,034.13    495,761.27
    Effective Gross Revenue                             924,581.95    972,521.50  1,031,401.67  1,083,208.40  1,143,559.43  1,180,481.34  1,215,895.78
    Less: Operating expenses                           -388,172.03   -405,541.99   -425,687.47   -444,606.64   -465,821.76   -482,034.13   -495,761.27
------------------------------------------------------------------------------------------------------------------------------------------------------
  Net Operating Income                                  536,409.92    566,979.51    605,714.20    638,601.76    677,737.68    698,447.22    720,134.52
  NOI margin                                                  0.58          0.58          0.59          0.59          0.59          0.59          0.59

  Net Operating Income                                  536,409.92    566,979.51    605,714.20    638,601.76    677,737.68    698,447.22    720,134.52
  Capital expenditures                                                -38,000.00    -76,000.00    -57,000.00         -0.00    -15,200.00         -0.00
  Capex funded by reserves                                             38,000.00     20,727.10     20,761.81          0.00     15,200.00          0.00
------------------------------------------------------------------------------------------------------------------------------------------------------
Adjusted NOI                                                          566,979.51    550,441.30    602,363.57    677,737.68    698,447.22    720,134.52
  Adjusted NOI                                                        566,979.51    550,441.30    602,363.57    677,737.68    698,447.22    720,134.52
  Debt service                                                       -413,320.56   -413,320.56   -413,320.56   -413,320.56   -413,320.56          0.00
------------------------------------------------------------------------------------------------------------------------------------------------------
Levered cash flow                                                     153,658.95    137,120.75    189,043.01    264,417.12    285,126.66    720,134.52
```

`performance.py`:

```txt
Unlevered investment performance
Start                                          2017-12-31  2018-12-31  2019-12-31  2020-12-31     2021-12-31
End                                2017-12-31  2018-12-31  2019-12-31  2020-12-31  2021-12-31     2022-12-31
  Purchase price                -9,775,000.00
  Buying costs                     -97,750.00
  Initial reserve funding          -19,000.00
  Unlevered property cash flow           0.00  566,979.51  550,441.30  602,363.57  677,737.68     698,447.22
  Sale price                                                                                   12,002,241.92
  Selling costs                                                                                  -240,044.84
  Reserve release                                                                                  28,210.87
------------------------------------------------------------------------------------------------------------
Total unlevered cash flow       -9,891,750.00  566,979.51  550,441.30  602,363.57  677,737.68  12,488,855.17
Unlevered IRR: 9.37%
Total initial investment: 9,891,750.00
Total return (cash distributions): 14,886,377.23
MOIC: 1.50x

Levered equity performance
Start                                              2017-12-31   2018-12-31   2019-12-31   2020-12-31     2021-12-31
End                                   2017-12-31   2018-12-31   2019-12-31   2020-12-31   2021-12-31     2022-12-31
  Total unlevered cash flow        -9,891,750.00   566,979.51   550,441.30   602,363.57   677,737.68  12,488,855.17
  Debt draw                         6,353,750.00
  Loan issuance fees                  -63,537.50
  Debt service                              0.00  -413,320.56  -413,320.56  -413,320.56  -413,320.56    -413,320.56
  Debt payoff                                                                                         -5,825,317.00
-------------------------------------------------------------------------------------------------------------------
Total levered cash flow to equity  -3,601,537.50   153,658.95   137,120.75   189,043.01   264,417.12   6,250,217.61
Levered IRR: 15.13%
Total initial investment: 3,601,537.50
Total return (cash distributions): 6,994,457.45
MOIC: 1.94x

Sources and uses at acquisition
  Acquisition price                9,775,000.00
  Buying costs                        97,750.00
  Loan issuance fees                  63,537.50
  Upfront reserve funding             19,000.00
Total uses                         9,955,287.50
-----------------------------------------------
  Senior debt                      6,353,750.00
  Equity investment                3,601,537.50
Total sources                      9,955,287.50

Debt metrics (coverage ratios in x)
Start                          2017-12-31  2018-12-31  2019-12-31  2020-12-31  2021-12-31
End                2017-12-31  2018-12-31  2019-12-31  2020-12-31  2021-12-31  2022-12-31
Debt yield (%)                       8.92        9.53       10.05       10.67       10.99
Interest coverage                    1.78        1.94        2.07        2.24        2.35
DSCR                                 1.37        1.47        1.55        1.64        1.69
```
