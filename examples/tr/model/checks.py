import sys
from datetime import date
from itertools import pairwise
from pathlib import Path

import pytest
from dateutil.relativedelta import relativedelta

from orcaset import Context, Period, PointSeriesDef, SpanSeriesDef

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from model import cash_flow
from model import dividends
from model.assets import cash, restricted_cash, total_assets
from model.data import BalanceSheet
from model.equity import (
    aoci_loss,
    capital_in_excess_of_par,
    class_b_common_stock,
    common_stock,
    noncontrolling_interests,
    retained_earnings,
    total_equity,
    treasury_stock,
)
from model.income import earnings_to_stockholders
from model.liabilities import total_liabilities

hist_balance_sheet = BalanceSheet()
test_dates = [date(2025, 12, 31) + (i * relativedelta(months=3, day=31)) for i in range(8)]


def point_value(ctx: Context, series: PointSeriesDef, dt: date) -> float:
    value = series.value(ctx, dt).eval()
    assert value is not None
    return value


def span_value(ctx: Context, series: SpanSeriesDef, period: Period) -> float:
    value = series.value(ctx, period).eval()
    assert value is not None
    return value


def assert_close(actual: float, expected: float) -> None:
    assert actual == pytest.approx(expected, abs=0.01)


def test_assets_equal_liabilities_plus_equity():
    ctx = Context()

    for dt in test_dates:
        assert_close(
            point_value(ctx, total_assets, dt),
            point_value(ctx, total_liabilities, dt) + point_value(ctx, total_equity, dt),
        )


def test_cash_and_restricted_cash_roll_forward_matches_cash_flow_change():
    ctx = Context()

    for prior_dt, current_dt in pairwise(test_dates):
        period = Period(prior_dt, current_dt)
        prior_cash = point_value(ctx, cash, prior_dt) + point_value(ctx, restricted_cash, prior_dt)
        current_cash = point_value(ctx, cash, current_dt) + point_value(
            ctx, restricted_cash, current_dt
        )

        assert_close(
            current_cash,
            prior_cash + span_value(ctx, cash_flow.cash_change, period),
        )


def test_projected_restricted_cash_roll_forward_matches_cash_flow_change():
    ctx = Context()

    for prior_dt, current_dt in pairwise(test_dates[1:]):
        period = Period(prior_dt, current_dt)

        assert_close(
            point_value(ctx, restricted_cash, current_dt),
            point_value(ctx, restricted_cash, prior_dt)
            + span_value(ctx, cash_flow.restricted_cash_change, period),
        )


def test_total_equity_roll_forward_includes_other_equity_changes():
    ctx = Context()
    other_equity_series = [
        common_stock,
        class_b_common_stock,
        capital_in_excess_of_par,
        aoci_loss,
        treasury_stock,
        noncontrolling_interests,
    ]

    for prior_dt, current_dt in pairwise(test_dates):
        period = Period(prior_dt, current_dt)
        retained_earnings_change = point_value(ctx, retained_earnings, current_dt) - point_value(
            ctx, retained_earnings, prior_dt
        )
        earnings_and_dividends = span_value(ctx, earnings_to_stockholders, period) - span_value(
            ctx, dividends.dividends_declared, period
        )
        retained_earnings_other_change = retained_earnings_change - earnings_and_dividends
        other_equity_change = retained_earnings_other_change + sum(
            point_value(ctx, series, current_dt) - point_value(ctx, series, prior_dt)
            for series in other_equity_series
        )

        assert_close(
            point_value(ctx, total_equity, current_dt),
            point_value(ctx, total_equity, prior_dt) + earnings_and_dividends + other_equity_change,
        )
