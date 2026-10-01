# Arcadia Gardens

Build a multifamily acquisition pro forma for **Arcadia Gardens**, a 76-unit apartment community in Phoenix, AZ. 

## Scenario assumptions

- Acquisition date: 2017-12-31
- Exit date: 2022-12-31

## Property detail

- Property name: Arcadia Gardens
- Location: Phoenix, AZ
- Number of units: 76
- Average rentable area per unit: 573 sq. ft.
- Parking spaces per unit: 1.13
- Rentable-to-gross area ratio: 80.0%
- Property taxes: 0.68% of acquisition price
- Property management fee: 3.00% of EGI

## Acquisition, exit, and debt assumptions

- Acquisition price: $9,775,000
- Acquisition costs: 1.0% of acquisition price
- Loan issuance fees: 1.0% of senior debt
- Acquisition LTV: 65.0% of acquisition price
- Upfront reserve funding: $19,000
- Loan interest rate: 5.0% assuming 12 30-day months and 360 days per year
- Loan amortization period: 30 years on monthly basis
- Loan maturity: 5 years
- Exit capitalization rate: 6.00% of NTM NOI
- Selling costs: 2.0% of gross sale price

## Operating assumptions

### FY17A historical inputs

- Market rent: $1.777777778 / RSF / month
- In-place rent: $1.60 / RSF / month
- Parking fee: $50.00 / space / month
- Insurance: $0.40 / GSF / year
- Utilities: $85.00 / unit / month
- Replacement reserves: $250.00 / unit / year
- Bad debt and concessions: (3.0%) of effective rent
- Utility reimbursements: 80.0% of utility expense
- General vacancy: 0.0% of potential gross revenue
- Sales, marketing, and administrative: 19.0% of EGI

### Annual projection assumptions

| | FY18 | FY19 | FY20 | FY21 | FY22 | FY23 and thereafter |
|---|---:|---:|---:|---:|---:|---:|
| Rental and parking income growth | 3.5% | 3.5% | 3.5% | 3.0% | 3.0% | 3.0% |
| In-place rent discount to market | 7.5% | 5.0% | 2.5% | 1.0% | 1.0% | 1.0% |
| Bad debt and concessions | (3.0%) | (2.0%) | (2.0%) | (1.0%) | (1.0%) | (1.0%) |
| Utility reimbursements | 83.0% | 86.0% | 89.0% | 92.0% | 95.0% | 95.0% |
| General vacancy | (1.0%) | (2.0%) | (3.0%) | (3.0%) | (3.0%) | (3.0%) |
| Sales, marketing, and administrative | 19.2% | 19.4% | 19.6% | 19.8% | 20.0% | 20.0% |
| Property-tax growth | 2.0% | 2.0% | 2.0% | 2.0% | 2.0% | 2.0% |
| Operating-expense growth | 3.0% | 3.0% | 3.0% | 3.0% | 3.0% | 3.0% |
| Capital expenditures ($/unit/year) | 500 | 1,000 | 750 | 0 | 200 | 0 |


## Pro forma structure

- PGR should include base rental income (market rent), loss to lease, bad debt and concessions, parking income, and utility reimbursements
- EGI = PGR less vacancy
- NOI = EGI less total operating expenses
- Adjusted NOI = NOI less capex offset by capex paid from reserves
- Cash flow to equity = adjusted NOI less debt P&I
- Include debt yield based off the total initial debt and TTM NOI
- Include TTM interest coverage and DSCR on NOI
- Cash flows for IRRs should include return of unspent replacement reserve

## Replacement reserve timing

- Fund the reserve at acquisition with the upfront reserve amount.
- Grow annual replacement reserve contributions with operating-expense growth and accrue them within each annual period on a calendar-month basis.
- Reserve-funded capex is the lesser of capex spending and the beginning reserve balance plus that period's contributions, floored at zero.
- Post reserve-funded capex draws at the end of each annual period. Roll the balance forward by adding contributions and subtracting those draws.
- Between annual boundaries, the reserve balance is the last posted balance plus contributions accrued since that boundary. Do not deduct future period-end draws early or double-count contributions at a boundary.
- Return the remaining reserve balance once at exit in both unlevered and levered investment cash flows.

## Outputs

- Source and uses table at acquisition
- NOI and NOI margin as a percent of EGI
- Leveraged and unleveraged IRR, total investment, total return, and MOIC
