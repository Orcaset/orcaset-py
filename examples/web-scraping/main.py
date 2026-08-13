# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Run the web-scraping nowcast and print a quarterly operating-revenue table."""

from model import (
    as_of_date,
    nowcast_spec,
    operating_revenue_stmt,
    quarter_label,
    reporting_quarters,
)
from scrape import TSA_URL, tsa_passengers

from orcaset import Context, fixed_width_table, isna


def _format_millions(value: float | None) -> str:
    return "" if value is None else f"{value:,.0f}"


def main() -> None:
    today = as_of_date()
    ctx = Context()
    spec = nowcast_spec(ctx, today)

    print("Southwest Airlines (LUV) operating revenue")
    print("$ millions")
    print()
    if spec is None:
        print("Current quarter is already in the historical CSV; no TSA nowcast applied.")
    else:
        current_tsa = ctx.get_at(tsa_passengers, spec.qtd)
        prior_tsa = ctx.get_at(tsa_passengers, spec.prior_qtd)
        if isna(current_tsa) or isna(prior_tsa) or prior_tsa == 0.0:
            raise RuntimeError("TSA QTD volumes are missing or zero; cannot nowcast")
        factor = current_tsa / prior_tsa
        print(
            f"Nowcast {quarter_label(spec.current_quarter.end)} passenger revenue "
            "from TSA checkpoint QTD vs the prior quarter."
        )
        print(f"Source: {TSA_URL}")
        print(
            f"TSA QTD {spec.qtd.start.isoformat()} → {spec.qtd.end.isoformat()}: {current_tsa:,.0f}"
        )
        print(
            f"TSA QTD {spec.prior_qtd.start.isoformat()} → {spec.prior_qtd.end.isoformat()}: "
            f"{prior_tsa:,.0f}"
        )
        print(f"QoQ QTD factor: {factor:.4f}")
        print(
            "Freight and other hold last reported values in the current quarter; "
            "later quarters follow last year's seasonal QoQ."
        )
    print()

    result = operating_revenue_stmt.values_for_periods(ctx, reporting_quarters(today))
    print(fixed_width_table(result, date_formatter=quarter_label, value_formatter=_format_millions))


if __name__ == "__main__":
    main()
