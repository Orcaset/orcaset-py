import marimo

__generated_with = "0.23.9"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _():
    import marimo as mo
    from datetime import date
    from dateutil.relativedelta import relativedelta
    import plotly.graph_objects as go
    from orcaset import Period, Stmt, Total, markdown_table, span, sum_spans
    from model import (
        income_stmt,
        bs_stmt,
        cf_stmt,
        ppe,
        Assumptions,
        IncomeAssumptions,
        ModelContext,
    )
    from model.income import total_revenue, total_cogs, sga, income_before_tax, net_earnings

    return (
        Assumptions,
        IncomeAssumptions,
        ModelContext,
        Period,
        Stmt,
        Total,
        bs_stmt,
        cf_stmt,
        date,
        go,
        income_before_tax,
        income_stmt,
        markdown_table,
        mo,
        net_earnings,
        ppe,
        relativedelta,
        sga,
        span,
        sum_spans,
        total_cogs,
        total_revenue,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Tootsie Roll

    Link to repository: [github.com/orcaset/orcaset-py/examples/tr](https://github.com/orcaset/orcaset-py/examples/tr)

    This notebook builds an interactive financial model for Tootsie Roll (TR) using Orcaset. It projects financials forward from historical filings, using the same statement structure as the filings.

    ## Project layout

    The model is packaged as a module in the `model` folder. Historicals are packaged with the module and parsed from the `model.data` folder. Model components are organized into files by logical components.

    ```
    tr/
    ├── README.md
    ├── notebook.py                  # This notebook
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
        └── data/                    # CSV files with historical data
            ├── historical-income.csv
            ├── historical-balance-sheet.csv
            └── historical-cash-flow.csv
    ```
    """)
    return


@app.function(hide_code=True)
def number_format(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value / 1000:,.0f}"


@app.cell(hide_code=True)
def _(IncomeAssumptions, mo):
    _defaults = IncomeAssumptions()
    product_growth = mo.ui.slider(
        start=-0.10,
        stop=0.25,
        step=0.005,
        value=_defaults.product_sales_growth_rate,
        label="Product sales growth (y/y)",
        show_value=True,
    )
    rental_growth = mo.ui.slider(
        start=-0.10,
        stop=0.25,
        step=0.005,
        value=_defaults.rental_revenue_growth_rate,
        label="Rental revenue growth (y/y)",
        show_value=True,
    )
    product_margin = mo.ui.slider(
        start=0.30,
        stop=0.70,
        step=0.005,
        value=_defaults.product_cogs_margin,
        label="Product COGS margin",
        show_value=True,
    )
    rental_margin = mo.ui.slider(
        start=0.30,
        stop=0.70,
        step=0.005,
        value=_defaults.rental_cogs_margin,
        label="Rental COGS margin",
        show_value=True,
    )
    sga_growth = mo.ui.slider(
        start=-0.10,
        stop=0.25,
        step=0.005,
        value=_defaults.sga_growth_rate,
        label="SG&A growth (y/y)",
        show_value=True,
    )
    tax_rate = mo.ui.slider(
        start=0.0,
        stop=0.40,
        step=0.005,
        value=_defaults.income_tax_rate,
        label="Income tax rate",
        show_value=True,
    )
    return (
        product_growth,
        product_margin,
        rental_growth,
        rental_margin,
        sga_growth,
        tax_rate,
    )


@app.cell(hide_code=True)
def _(
    Assumptions,
    IncomeAssumptions,
    ModelContext,
    product_growth,
    product_margin,
    rental_growth,
    rental_margin,
    sga_growth,
    tax_rate,
):
    assumptions = Assumptions(
        income=IncomeAssumptions(
            product_sales_growth_rate=product_growth.value,
            rental_revenue_growth_rate=rental_growth.value,
            product_cogs_margin=product_margin.value,
            rental_cogs_margin=rental_margin.value,
            sga_growth_rate=sga_growth.value,
            income_tax_rate=tax_rate.value,
        )
    )
    ctx = ModelContext(assumptions)
    return (ctx,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Visualize Performance

    Before printing out the statements, this chart quickly shows operating results visually by graphing key line items over time. Unsurprisingly there is a strong seaonal trend with Q3 peaks leading into the Halloween and Christmas holidays.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    proj_qtrs = mo.ui.slider(start=0, stop=20, value=8, label="Change projected periods", show_value=True)
    return (proj_qtrs,)


@app.cell(hide_code=True)
def _(
    Period,
    ctx,
    date,
    go,
    income_before_tax,
    net_earnings,
    proj_qtrs,
    relativedelta,
    sga,
    total_cogs,
    total_revenue,
):
    hist_end = date(2026, 3, 31)
    plot_end = hist_end + relativedelta(months=3 * proj_qtrs.value, day=31)
    plot_periods = Period.list(date(2023, 12, 31), relativedelta(months=3, day=31), plot_end)
    plt_values = {}
    plt_values["Total revenue"] = [total_revenue.value(ctx, p).eval() for p in plot_periods]
    plt_values["Total COGS"] = [total_cogs.value(ctx, p).eval() for p in plot_periods]
    plt_values["SG&A"] = [sga.value(ctx, p).eval() for p in plot_periods]
    plt_values["Earnings before interest"] = [
        income_before_tax.value(ctx, p).eval() for p in plot_periods
    ]
    plt_values["Net earnings"] = [
        net_earnings.value(ctx, p).eval() for p in plot_periods
    ]

    revenue_fig = go.Figure()
    for _label, _values in plt_values.items():
        revenue_fig.add_trace(
            go.Scatter(
                x=[p.end for p in plot_periods],
                y=_values,
                mode="lines",
                name=_label,
            )
        )
    revenue_fig.add_vline(
        x="2026-05-15",
        line_dash="dash",
        line_color="gray",
        annotation_text="Historical | Projected",
        annotation_position="top",
    )
    revenue_fig.update_layout(
        title="Quarterly Operating Performance",
        yaxis_title="USD",
        legend_title=None,
    )
    return


@app.cell(hide_code=True)
def _(
    mo,
    product_growth,
    product_margin,
    proj_qtrs,
    rental_growth,
    rental_margin,
    sga_growth,
    tax_rate,
):
    mo.vstack([
        mo.md("**Assumptions**"),
        mo.hstack(
            [
                mo.vstack([product_growth, rental_growth, sga_growth]),
                mo.vstack([product_margin, rental_margin, tax_rate]),
            ],
            justify="start",
            gap=2,
        ),
        proj_qtrs,
        "Orcaset models running in marimo are fully reactive and interactive. Use the sliders to change model assumptions. The chart and the statements below recompute automatically.",
    ])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Print Statements

    This section prints each of the three statements to markdown. Statement format follows the same structure as TR's reported statements. Expande each section to vew the statement.
    """)
    return


@app.cell(hide_code=True)
def _(
    Period,
    Stmt,
    bs_stmt,
    cf_stmt,
    ctx,
    date,
    income_stmt,
    markdown_table,
    mo,
    relativedelta,
):
    query_periods = Period.list(date(2024, 12, 31), relativedelta(months=3, day=31), date(2026, 12, 31))
    income = Stmt(income_stmt)
    cf = Stmt(cf_stmt)
    bs = Stmt(bs_stmt)

    income_tbl = markdown_table(income.values(ctx, query_periods), value_formatter=number_format)
    bs_tbl = markdown_table(bs.values(ctx, query_periods), value_formatter=number_format)
    cf_tbl = markdown_table(cf.values(ctx, query_periods), value_formatter=number_format)
    mo.accordion({"Income": mo.md(income_tbl), "Balance sheet": bs_tbl, "Cash flow": cf_tbl})
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Fixed Assets Schedule

    Capex is projected at the trailing two-year quarterly average and split between
    buildings and machinery in proportion to each class's share of historical gross
    balance growth (overridable by assumption). Depreciation then has two parts:

    - **Existing PPE**: TR does not disclose a runoff schedule, so the existing net
      depreciable base runs off as a single cohort at the trailing-year reported
      run-rate until exhausted, keeping projected depreciation continuous with
      historicals.
    - **New capex cohorts**: each projected quarter of class capex becomes a cohort
      depreciating straight-line over the class useful life (35 years for buildings,
      12 for machinery by default), starting the quarter after the spend.

    The tables below show the capex split and cohort-level depreciation detail.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    fa_qtrs = mo.ui.slider(
        start=1,
        stop=20,
        value=5,
        label="Display quarters",
        show_value=True,
    )
    return (fa_qtrs,)


@app.cell(hide_code=True)
def _(
    Period,
    Stmt,
    Total,
    ctx,
    date,
    fa_qtrs,
    markdown_table,
    mo,
    ppe,
    relativedelta,
    span,
    sum_spans,
):
    fa_start = date(2026, 3, 31)
    fa_periods = Period.list(
        fa_start,
        relativedelta(months=3, day=31),
        fa_start + relativedelta(months=3 * fa_qtrs.value, day=31),
    )

    additions = span.sum(
        [ppe.building_capex, ppe.machinery_capex],
        agg=sum_spans(0.0),
        label="Total additions",
    )
    capex_stmt = Stmt(Total(additions, [ppe.building_capex, ppe.machinery_capex]))

    cohort_keys = list(ppe.capex_cohort_keys(fa_periods[-1]))
    building_cohorts = [ppe.building_depreciation_cohorts.get(ctx, key) for key in cohort_keys]
    machinery_cohorts = [ppe.machinery_depreciation_cohorts.get(ctx, key) for key in cohort_keys]
    depreciation_stmt = Stmt(
        Total(
            ppe.depreciation,
            [
                ppe.existing_depreciation,
                Total(ppe.building_depreciation, building_cohorts),
                Total(ppe.machinery_depreciation, machinery_cohorts),
            ],
        )
    )

    mo.vstack([
        fa_qtrs,
        mo.md("**Capital expenditures**"),
        mo.md(markdown_table(capex_stmt.values(ctx, fa_periods), value_formatter=number_format)),
        mo.md("**Depreciation**"),
        mo.md(
            markdown_table(depreciation_stmt.values(ctx, fa_periods), value_formatter=number_format)
        ),
    ])
    return


if __name__ == "__main__":
    app.run()
