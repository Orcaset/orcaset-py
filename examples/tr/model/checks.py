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
from model.equity import total_equity
from model.income import net_earnings
from model.liabilities import total_liabilities

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


def test_projected_total_equity_roll_forward_matches_income_and_cash_flow_changes():
    ctx = Context()

    for prior_dt, current_dt in pairwise(test_dates[1:]):
        period = Period(prior_dt, current_dt)
        equity_flow = (
            span_value(ctx, net_earnings, period)
            - span_value(ctx, dividends.dividends_declared, period)
            + span_value(ctx, cash_flow.share_repurchases, period)
        )

        assert_close(
            point_value(ctx, total_equity, current_dt),
            point_value(ctx, total_equity, prior_dt) + equity_flow,
        )
