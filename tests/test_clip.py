from datetime import date

import pytest
from dateutil.relativedelta import relativedelta

from orcaset import (
    YF,
    Chain,
    Context,
    Key,
    Period,
    Series,
    clip_dates,
    clip_periods,
    concat_cells,
    unfold_cells,
)
from orcaset.maybe import Maybe, isna
from orcaset.query import accrue, accrue_drop, exact, last

MONTH = relativedelta(months=1, day=31)
Y2026 = Period(date(2025, 12, 31), date(2026, 12, 31))
Y2027 = Period(date(2026, 12, 31), date(2027, 12, 31))
Y2028 = Period(date(2027, 12, 31), date(2028, 12, 31))
FREE = Period(date(2026, 9, 30), date(2027, 3, 31))

rent = Series.of("rent", accrue(YF.cmonthly), [(Y2026, 100.0), (Y2027, 110.0)])


def items[K: Key, V](ctx: Context, cells: Chain[K, V]) -> list[tuple[K, V]]:
    result: list[tuple[K, V]] = []
    node = ctx.get(cells)
    while node is not None:
        result.append((node.key, ctx.get(node.value)))
        node = ctx.get(node.tail)
    return result


def test_clip_periods_trims_cells_and_values_them_by_the_source():
    basis = clip_periods("basis", rent, FREE.start, FREE.end)
    ctx = Context()
    assert items(ctx, basis.cells) == [
        (Period(FREE.start, Y2026.end), 25.0),
        (Period(Y2027.start, FREE.end), 27.5),
    ]


def test_clip_periods_forwards_trimmed_queries_and_is_na_outside():
    basis = clip_periods("basis", rent, FREE.start, FREE.end)
    ctx = Context()
    # Partial overlaps keep only the time inside the bounds, so a step-up is not averaged.
    assert ctx.get_at(basis, Y2026) == 25.0
    assert ctx.get_at(basis, Y2027) == 27.5
    assert ctx.get_at(basis, Period(Y2026.start, Y2027.end)) == 52.5
    assert isna(ctx.get_at(basis, Y2028))


def test_clip_periods_bounds_are_optional():
    ctx = Context()
    from_2027 = clip_periods("from 2027", rent, start=Y2027.start)
    through_2026 = clip_periods("through 2026", rent, end=Y2026.end)
    assert [k for k, _ in items(ctx, from_2027.cells)] == [Y2027]
    assert [k for k, _ in items(ctx, through_2026.cells)] == [Y2026]
    assert clip_periods("all", rent).cells is not rent.cells
    assert items(ctx, clip_periods("all", rent).cells) == [(Y2026, 100.0), (Y2027, 110.0)]


def test_clip_periods_stops_without_walking_past_the_end():
    def step(period: Period) -> tuple[Period, float, Period]:
        assert period.start < date(2026, 6, 30), "walked past the clip end"
        return period, 10.0, period.from_end(MONTH)

    monthly = Series.unfold(
        "monthly", accrue(YF.cmonthly), seed=Period(Y2026.start, date(2026, 1, 31)), step=step
    )
    clipped = clip_periods("clipped", monthly, date(2026, 1, 31), date(2026, 3, 31))
    ctx = Context()
    assert ctx.get_at(clipped, Period(date(2026, 1, 31), date(2026, 3, 31))) == 20.0
    assert len(items(ctx, clipped.cells)) == 2


def test_concatenated_clips_agree_with_direct_queries():
    basis = clip_periods("basis", rent, FREE.start, FREE.end)
    joined = Series(
        "joined",
        concat_cells("joined", Series.of("chains", exact, [(0, basis.cells)]).cells),
        accrue_drop(YF.cmonthly),
    )
    ctx = Context()
    for q in (Y2026, Y2027):
        assert ctx.get_at(joined, q) == ctx.get_at(basis, q)
    assert ctx.get_at(joined, Y2028) == 0.0


D1, D2, D3, D4 = date(2026, 3, 31), date(2026, 6, 30), date(2026, 9, 30), date(2026, 12, 31)
flows: Series[date, float, Maybe[float]] = Series.of(
    "flows", last, [(D1, 1.0), (D2, 2.0), (D3, 3.0), (D4, 4.0)]
)


def test_clip_dates_keeps_start_exclusive_end_inclusive_and_passes_value_rules_through():
    clipped = clip_dates("clipped", flows, D1, D3)
    ctx = Context()
    assert items(ctx, clipped.cells) == [(D2, 2.0), (D3, 3.0)]
    head = ctx.get(flows.cells)
    assert head is not None
    source_node = ctx.get(head.tail)  # D2
    clipped_node = ctx.get(clipped.cells)
    assert source_node is not None and clipped_node is not None
    assert clipped_node.value is source_node.value


@pytest.mark.parametrize(
    ("q", "expected"),
    [(D1, None), (D2, 2.0), (date(2026, 8, 31), 2.0), (D3, 3.0), (D4, None)],
)
def test_clip_dates_answers_inside_from_clipped_cells_and_is_na_outside(
    q: date, expected: float | None
):
    clipped = clip_dates("clipped", flows, D1, D3)
    answer = Context().get_at(clipped, q)
    assert isna(answer) if expected is None else answer == expected


def test_clip_dates_look_back_cannot_reach_before_start():
    clipped = clip_dates("clipped", flows, date(2026, 4, 30))
    # The source's last value at May 31 is from March 31, which is outside the clip.
    assert isna(Context().get_at(clipped, date(2026, 5, 31)))
    assert Context().get_at(clipped, date(2026, 7, 31)) == 2.0


def test_clip_dates_stops_without_walking_past_the_end():
    def step(day: date) -> tuple[date, float, date]:
        assert day <= date(2026, 4, 30), "walked past the clip end"
        return day, float(day.month), day + MONTH

    monthly = unfold_cells("monthly", seed=date(2026, 1, 31), step=step)
    clipped = clip_dates(
        "clipped", Series("monthly", monthly, exact), date(2026, 1, 31), date(2026, 3, 31)
    )
    assert [k for k, _ in items(Context(), clipped.cells)] == [date(2026, 2, 28), date(2026, 3, 31)]
