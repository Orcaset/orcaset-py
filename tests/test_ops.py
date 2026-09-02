from datetime import date

import pytest
from dateutil.relativedelta import relativedelta

from orcaset import (
    Cell,
    Cells,
    Context,
    Maybe,
    Na,
    Period,
    Series,
    Step,
    Thunk,
    date_union,
    exact,
    get,
    isna,
    keys_until,
    last,
    merge_cells,
    ops,
    period_union,
)

MONTH = relativedelta(months=1)


def covering(q: Period, cells: Cells[Period, float]) -> Step[Maybe[float]]:
    """Test ``QueryFn``: value of the cell whose period contains ``q``."""
    node = yield from get(cells)
    while node is not None:
        if node.key < q:
            node = yield from get(node.tail)
        elif node.key.start <= q.start and q.end <= node.key.end:
            return (yield from get(node.cell))
        else:
            return Na
    return Na


def prorated(q: Period, cells: Cells[Period, float]) -> Step[Maybe[float]]:
    """Test ``QueryFn``: day-count share of the covering cell's value."""
    node = yield from get(cells)
    while node is not None:
        if node.key < q:
            node = yield from get(node.tail)
        elif node.key.start <= q.start and q.end <= node.key.end:
            value = yield from get(node.cell)
            return value * (q.end - q.start).days / (node.key.end - node.key.start).days
        else:
            return Na
    return Na


def month(index: int) -> Period:
    return Period(date(2026, index, 1), date(2026, index + 1, 1))


def test_add_dates_sums_and_propagates_na():
    d1, d2, d3 = date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)
    a = Series.of("A", exact, [(d1, 1.0), (d2, 2.0)])
    b = Series.of("B", exact, [(d2, 10.0), (d3, 20.0)])
    total = ops.add("Total", a, b, merge_keys=date_union)
    ctx = Context()

    assert ctx.get(Cell("keys", lambda: keys_until(total.cells, d3))) == [d1, d2, d3]
    assert ctx.get_at(total, d2) == 12.0
    # Union domain: keys where a source answers Na (exact miss) are Na.
    assert isna(ctx.get_at(total, d1))
    assert isna(ctx.get_at(total, d3))


def test_add_is_nary():
    d = date(2026, 1, 31)
    a = Series.of("A", exact, [(d, 1.0)])
    b = Series.of("B", exact, [(d, 2.0)])
    c = Series.of("C", exact, [(d, 3.0)])
    total = ops.add("Total", a, b, c, merge_keys=date_union)

    assert Context().get_at(total, d) == 6.0


def test_mul_splits_periods_and_queries_sources_by_piece():
    year = Period(date(2026, 1, 1), date(2027, 1, 1))
    months = [month(1), month(2), month(3)]
    price = Series.of("Price", covering, [(year, 10.0)])
    volume = Series.of("Volume", exact, list(zip(months, [100.0, 200.0, 300.0])))
    revenue = ops.mul("Revenue", price, volume, merge_keys=period_union)
    ctx = Context()

    rest_of_year = Period(date(2026, 4, 1), date(2027, 1, 1))
    keys = ctx.get(Cell("keys", lambda: keys_until(revenue.cells, rest_of_year)))
    assert keys == [*months, rest_of_year]
    assert ctx.get_at(revenue, months[0]) == 1000.0
    assert ctx.get_at(revenue, months[1]) == 2000.0
    assert ctx.get_at(revenue, months[2]) == 3000.0
    # Past the volume domain the annual price still answers but volume is Na.
    assert isna(ctx.get_at(revenue, rest_of_year))


def test_query_delegates_to_sources_off_spine():
    q1 = Period(date(2026, 1, 1), date(2026, 4, 1))
    rent = Series.of("Rent", prorated, [(q1, 9_000.0)])
    utilities = Series.of("Utilities", prorated, list(zip([month(1), month(2), month(3)], [310.0, 280.0, 310.0])))
    total = ops.add("Total", rent, utilities, merge_keys=period_union)
    ctx = Context()

    # Spine keys are the months; rent prorates itself by day count.
    assert ctx.get_at(total, month(1)) == 9_000.0 * 31 / 90 + 310.0
    # A key that is on no source's spine and finer than every spine cell.
    half_jan = Period(date(2026, 1, 1), date(2026, 1, 16))
    assert ctx.get_at(total, half_jan) == 9_000.0 * 15 / 90 + 310.0 * 15 / 31
    # A key coarser than the spine: rent answers whole, utilities has no
    # covering cell and answers Na, which propagates.
    assert isna(ctx.get_at(total, q1))


def test_query_respects_each_source_own_semantics():
    d1, d2 = date(2026, 1, 31), date(2026, 2, 28)
    stock = Series.of("Stock", last, [(d1, 100.0)])
    flow = Series.of("Flow", exact, [(d1, 1.0), (d2, 2.0)])
    total = ops.add("Total", stock, flow, merge_keys=date_union)

    # Stock carries forward under `last`; flow is exact. No single query on
    # the result could express both, so the result asks each source.
    assert Context().get_at(total, d2) == 102.0


def test_mul_off_spine_does_not_aggregate_products():
    q1 = Period(date(2026, 1, 1), date(2026, 4, 1))
    months = [month(1), month(2), month(3)]
    price = Series.of("Price", covering, [(q1, 10.0)])
    volume = Series.of("Volume", exact, list(zip(months, [100.0, 200.0, 300.0])))
    revenue = ops.mul("Revenue", price, volume, merge_keys=period_union)

    # Volume has no exact Q1 cell, so the product is Na rather than a silently
    # wrong price(Q1) * volume(Q1).
    assert isna(Context().get_at(revenue, q1))


def test_nary_piece_truncated_by_later_operand():
    def p(m1: int, m2: int) -> Period:
        return Period(date(2026, m1, 1), date(2026, m2, 1))

    a = Series.of("A", exact, [(p(1, 7), 1.0)])
    b = Series.of("B", exact, [(p(3, 5), 1.0)])
    c = Series.of("C", exact, [(p(2, 6), 1.0)])
    total = ops.add("Total", a, b, c, merge_keys=period_union)

    keys = Context().get(Cell("keys", lambda: keys_until(total.cells, p(6, 7))))
    assert keys == [p(1, 2), p(2, 3), p(3, 5), p(5, 6), p(6, 7)]


def test_merge_is_lazy_and_never_forces_source_cells():
    def poison() -> float:
        raise AssertionError("source cell was forced")

    def infinite(name: str, start: date) -> Series[date, date, float, Maybe[float]]:
        return Series.unfold(
            name,
            exact,
            seed=start,
            step=lambda d: (d, Thunk(poison), d + MONTH),
        )

    a = infinite("A", date(2026, 1, 31))
    b = infinite("B", date(2026, 2, 15))
    total = ops.add("Total", a, b, merge_keys=date_union)

    keys = Context().get(Cell("keys", lambda: keys_until(total.cells, date(2026, 3, 1))))
    assert keys == [date(2026, 1, 31), date(2026, 2, 15), date(2026, 2, 28)]


def test_sub_and_div():
    d = date(2026, 1, 31)
    a = Series.of("A", exact, [(d, 10.0)])
    b = Series.of("B", exact, [(d, 4.0)])
    diff = ops.sub("Diff", a, b, merge_keys=date_union)
    ratio = ops.div("Ratio", a, b, merge_keys=date_union)
    ctx = Context()

    assert ctx.get_at(diff, d) == 6.0
    assert ctx.get_at(ratio, d) == 2.5


def test_fill_substitutes_for_na_sources():
    d1, d2, d3, d4 = date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)
    a = Series.of("A", exact, [(d1, 1.0), (d2, 2.0)])
    b = Series.of("B", exact, [(d2, 10.0), (d3, 20.0)])
    total = ops.add("Total", a, b, merge_keys=date_union, fill=0.0)
    ctx = Context()

    assert ctx.get_at(total, d1) == 1.0
    assert ctx.get_at(total, d2) == 12.0
    assert ctx.get_at(total, d3) == 20.0
    # Simple substitution: outside every domain each source is filled too.
    assert ctx.get_at(total, d4) == 0.0


def test_fill_applies_to_every_op_and_both_sides():
    d = date(2026, 1, 31)
    a = Series.of("A", exact, [(d, 10.0)])
    empty = Series.of("Empty", exact, [])
    ctx = Context()

    assert ctx.get_at(ops.mul("P", a, empty, merge_keys=date_union, fill=1.0), d) == 10.0
    assert ctx.get_at(ops.mul("P0", a, empty, merge_keys=date_union, fill=0.0), d) == 0.0
    assert ctx.get_at(ops.sub("S", a, empty, merge_keys=date_union, fill=0.0), d) == 10.0
    assert ctx.get_at(ops.sub("S2", empty, a, merge_keys=date_union, fill=0.0), d) == -10.0
    assert ctx.get_at(ops.div("D", empty, a, merge_keys=date_union, fill=0.0), d) == 0.0
    with pytest.raises(ZeroDivisionError):
        ctx.get_at(ops.div("D0", a, empty, merge_keys=date_union, fill=0.0), d)


def test_combine_hands_na_to_fn_unchanged():
    d = date(2026, 1, 31)
    a = Series.of("A", exact, [(d, 10.0)])
    empty = Series.of("Empty", exact, [])
    seen: list[list[Maybe[float]]] = []

    def fn(values):
        seen.append(list(values))
        return sum(v for v in values if not isna(v))

    total = ops.combine("Total", (a, empty), fn=fn, merge_keys=date_union)

    assert Context().get_at(total, d) == 10.0
    assert seen == [[10.0, Na]]


def test_filled_lifts_float_fold():
    assert isna(ops.filled(sum)([1.0, Na]))
    assert ops.filled(sum, 0.0)([1.0, Na]) == 1.0
    assert ops.filled(sum, 0.0)([Na, Na]) == 0.0
    assert ops.filled(sum)([1.0, 2.0]) == 3.0


def test_fill_default_still_propagates_na():
    d = date(2026, 1, 31)
    a = Series.of("A", exact, [(d, 10.0)])
    empty = Series.of("Empty", exact, [])

    assert isna(Context().get_at(ops.add("T", a, empty, merge_keys=date_union), d))


def test_buggy_key_merge_raises():
    d1, d2 = date(2026, 1, 31), date(2026, 2, 28)
    a = Series.of("A", exact, [(d1, 1.0)])
    b = Series.of("B", exact, [(d2, 1.0)])

    def bad(left: date, right: date) -> tuple[date, date | None, date | None]:
        return left, left, right

    total = ops.add("Total", a, b, merge_keys=bad)

    # Queries delegate to sources and never touch the merged chain, so the
    # refold check surfaces on a chain walk.
    with pytest.raises(ValueError, match="refold"):
        Context().get(Cell("keys", lambda: keys_until(total.cells, d2)))


def test_merge_cells_standalone_plain_values():
    d1, d2 = date(2026, 1, 31), date(2026, 2, 28)
    a = Series.of("A", exact, [(d1, 0.0)])
    b = Series.of("B", exact, [(d2, 0.0)])
    merged = Series(
        "Merged",
        merge_cells("Merged", [a.cells, b.cells], date_union, lambda k: float(k.month)),
        exact,
    )
    ctx = Context()

    assert ctx.get_at(merged, d1) == 1.0
    assert ctx.get_at(merged, d2) == 2.0
