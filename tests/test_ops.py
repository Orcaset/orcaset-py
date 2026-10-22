from collections.abc import Sequence
from datetime import date

import pytest
from dateutil.relativedelta import relativedelta

from orcaset import (
    Chain,
    Context,
    Effect,
    Fn,
    Period,
    Rule,
    Series,
    Thunk,
    Val,
    date_union,
    get,
    keys_until,
    merge_cells,
    ops,
    period_union,
)
from orcaset.maybe import Maybe, Na, isna, map2_some, sum_some
from orcaset.query import exact, last

MONTH = relativedelta(months=1)


def covering(q: Period, cells: Chain[Period, float]) -> Effect[Maybe[float]]:
    """Test ``QueryFn``: value of the cell whose period contains ``q``."""
    node = yield from get(cells)
    while node is not None:
        if node.key < q:
            node = yield from get(node.tail)
        elif node.key.start <= q.start and q.end <= node.key.end:
            return (yield from get(node.value))
        else:
            return Na
    return Na


def prorated(q: Period, cells: Chain[Period, float]) -> Effect[Maybe[float]]:
    """Test ``QueryFn``: day-count share of the covering cell's value."""
    node = yield from get(cells)
    while node is not None:
        if node.key < q:
            node = yield from get(node.tail)
        elif node.key.start <= q.start and q.end <= node.key.end:
            value = yield from get(node.value)
            return value * (q.end - q.start).days / (node.key.end - node.key.start).days
        else:
            return Na
    return Na


def month(index: int) -> Period:
    return Period(date(2026, index, 1), date(2026, index + 1, 1))


def test_add_dates_sums_and_propagates_na():
    d1, d2, d3 = date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)
    a = Series.of(exact, [(d1, 1.0), (d2, 2.0)], name="A")
    b = Series.of(exact, [(d2, 10.0), (d3, 20.0)], name="B")
    total = ops.add(a, b, merge_keys=date_union, name="Total")
    ctx = Context()

    assert ctx.get(Fn(lambda: keys_until(total.cells, d3), name="keys")) == [d1, d2, d3]
    assert ctx.get_at(total, d2) == 12.0
    # Union domain: keys where a source answers Na (exact miss) are Na.
    assert isna(ctx.get_at(total, d1))
    assert isna(ctx.get_at(total, d3))


def test_add_is_nary():
    d = date(2026, 1, 31)
    a = Series.of(exact, [(d, 1.0)], name="A")
    b = Series.of(exact, [(d, 2.0)], name="B")
    c = Series.of(exact, [(d, 3.0)], name="C")
    total = ops.add(a, b, c, merge_keys=date_union, name="Total")

    assert Context().get_at(total, d) == 6.0


def test_mul_splits_periods_and_queries_sources_by_piece():
    year = Period(date(2026, 1, 1), date(2027, 1, 1))
    months = [month(1), month(2), month(3)]
    price = Series.of(covering, [(year, 10.0)], name="Price")
    volume = Series.of(exact, list(zip(months, [100.0, 200.0, 300.0])), name="Volume")
    revenue = ops.mul(price, volume, merge_keys=period_union, name="Revenue")
    ctx = Context()

    rest_of_year = Period(date(2026, 4, 1), date(2027, 1, 1))
    keys = ctx.get(Fn(lambda: keys_until(revenue.cells, rest_of_year), name="keys"))
    assert keys == [*months, rest_of_year]
    assert ctx.get_at(revenue, months[0]) == 1000.0
    assert ctx.get_at(revenue, months[1]) == 2000.0
    assert ctx.get_at(revenue, months[2]) == 3000.0
    # Past the volume domain the annual price still answers but volume is Na.
    assert isna(ctx.get_at(revenue, rest_of_year))


def test_query_delegates_to_sources_off_spine():
    q1 = Period(date(2026, 1, 1), date(2026, 4, 1))
    rent = Series.of(prorated, [(q1, 9_000.0)], name="Rent")
    utilities = Series.of(
        prorated, list(zip([month(1), month(2), month(3)], [310.0, 280.0, 310.0])), name="Utilities"
    )
    total = ops.add(rent, utilities, merge_keys=period_union, name="Total")
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
    stock = Series.of(last, [(d1, 100.0)], name="Stock")
    flow = Series.of(exact, [(d1, 1.0), (d2, 2.0)], name="Flow")
    total = ops.add(stock, flow, merge_keys=date_union, name="Total")

    # Stock carries forward under `last`; flow is exact. No single query on
    # the result could express both, so the result asks each source.
    assert Context().get_at(total, d2) == 102.0


def test_mul_off_spine_does_not_aggregate_products():
    q1 = Period(date(2026, 1, 1), date(2026, 4, 1))
    months = [month(1), month(2), month(3)]
    price = Series.of(covering, [(q1, 10.0)], name="Price")
    volume = Series.of(exact, list(zip(months, [100.0, 200.0, 300.0])), name="Volume")
    revenue = ops.mul(price, volume, merge_keys=period_union, name="Revenue")

    # Volume has no exact Q1 cell, so the product is Na rather than a silently
    # wrong price(Q1) * volume(Q1).
    assert isna(Context().get_at(revenue, q1))


def test_nary_piece_truncated_by_later_operand():
    def p(m1: int, m2: int) -> Period:
        return Period(date(2026, m1, 1), date(2026, m2, 1))

    a = Series.of(exact, [(p(1, 7), 1.0)], name="A")
    b = Series.of(exact, [(p(3, 5), 1.0)], name="B")
    c = Series.of(exact, [(p(2, 6), 1.0)], name="C")
    total = ops.add(a, b, c, merge_keys=period_union, name="Total")

    keys = Context().get(Fn(lambda: keys_until(total.cells, p(6, 7)), name="keys"))
    assert keys == [p(1, 2), p(2, 3), p(3, 5), p(5, 6), p(6, 7)]


def test_merge_is_lazy_and_never_forces_source_cells():
    def poison() -> float:
        raise AssertionError("source cell was forced")

    def infinite(name: str, start: date) -> Series[date, float, Maybe[float]]:
        def step(day: date) -> tuple[date, Thunk[float], date]:
            return day, Thunk(poison), day + MONTH

        return Series.unfold(exact, seed=start, step=step, name=name)

    a = infinite("A", date(2026, 1, 31))
    b = infinite("B", date(2026, 2, 15))
    total = ops.add(a, b, merge_keys=date_union, name="Total")

    keys = Context().get(Fn(lambda: keys_until(total.cells, date(2026, 3, 1)), name="keys"))
    assert keys == [date(2026, 1, 31), date(2026, 2, 15), date(2026, 2, 28)]


def test_sub_and_div():
    d = date(2026, 1, 31)
    a = Series.of(exact, [(d, 10.0)], name="A")
    b = Series.of(exact, [(d, 4.0)], name="B")
    diff = ops.sub(a, b, merge_keys=date_union, name="Diff")
    ratio = ops.div(a, b, merge_keys=date_union, name="Ratio")
    ctx = Context()

    assert ctx.get_at(diff, d) == 6.0
    assert ctx.get_at(ratio, d) == 2.5


def test_fill_substitutes_for_na_sources():
    d1, d2, d3, d4 = date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)
    a = Series.of(exact, [(d1, 1.0), (d2, 2.0)], name="A")
    b = Series.of(exact, [(d2, 10.0), (d3, 20.0)], name="B")
    total = ops.add(a, b, merge_keys=date_union, fill=0.0, name="Total")
    ctx = Context()

    assert ctx.get_at(total, d1) == 1.0
    assert ctx.get_at(total, d2) == 12.0
    assert ctx.get_at(total, d3) == 20.0
    # Simple substitution: outside every domain each source is filled too.
    assert ctx.get_at(total, d4) == 0.0


def test_fill_applies_to_every_op_and_both_sides():
    d = date(2026, 1, 31)
    a = Series.of(exact, [(d, 10.0)], name="A")
    empty = Series.of(exact, [], name="Empty")
    ctx = Context()

    assert ctx.get_at(ops.mul(a, empty, merge_keys=date_union, fill=1.0, name="P"), d) == 10.0
    assert ctx.get_at(ops.mul(a, empty, merge_keys=date_union, fill=0.0, name="P0"), d) == 0.0
    assert ctx.get_at(ops.sub(a, empty, merge_keys=date_union, fill=0.0, name="S"), d) == 10.0
    assert ctx.get_at(ops.sub(empty, a, merge_keys=date_union, fill=0.0, name="S2"), d) == -10.0
    assert ctx.get_at(ops.div(empty, a, merge_keys=date_union, fill=0.0, name="D"), d) == 0.0
    with pytest.raises(ZeroDivisionError):
        ctx.get_at(ops.div(a, empty, merge_keys=date_union, fill=0.0, name="D0"), d)


def test_mapn_hands_na_to_fn_unchanged():
    d = date(2026, 1, 31)
    a = Series.of(exact, [(d, 10.0)], name="A")
    empty = Series.of(exact, [], name="Empty")
    seen: list[list[Maybe[float]]] = []

    def fn(values: Sequence[Maybe[float]]) -> float:
        seen.append(list(values))
        return sum(v for v in values if not isna(v))

    total = ops.mapn((a, empty), fn=fn, merge_keys=date_union, name="Total")

    assert Context().get_at(total, d) == 10.0
    assert seen == [[10.0, Na]]


def test_mapn_accepts_effectful_fn():
    d = date(2026, 1, 31)
    left = Series.of(exact, [(d, 10.0)], name="Left")
    right = Series.of(exact, [(d, 20.0)], name="Right")
    offset = Val(5.0, name="Offset")

    def fn(values: Sequence[Maybe[float]]) -> Effect[float]:
        resolved = yield from get(offset)
        return sum(value for value in values if not isna(value)) + resolved

    combined = ops.mapn((left, right), fn=fn, merge_keys=date_union, name="Combined")
    ctx = Context()

    assert ctx.get_at(combined, d) == 35.0
    assert ctx.depends_on((combined, d), offset)


def test_fill_default_still_propagates_na():
    d = date(2026, 1, 31)
    a = Series.of(exact, [(d, 10.0)], name="A")
    empty = Series.of(exact, [], name="Empty")

    assert isna(Context().get_at(ops.add(a, empty, merge_keys=date_union, name="T"), d))


def test_buggy_key_merge_raises():
    d1, d2 = date(2026, 1, 31), date(2026, 2, 28)
    a = Series.of(exact, [(d1, 1.0)], name="A")
    b = Series.of(exact, [(d2, 1.0)], name="B")

    def bad(left: date, right: date) -> tuple[date, date | None, date | None]:
        return left, left, right

    total = ops.add(a, b, merge_keys=bad, name="Total")

    # Queries delegate to sources and never touch the merged chain, so the
    # refold check surfaces on a chain walk.
    with pytest.raises(ValueError, match="refold"):
        Context().get(Fn(lambda: keys_until(total.cells, d2), name="keys"))


def test_map_keeps_spine_and_maps_queries():
    q1 = Period(date(2026, 1, 1), date(2026, 4, 1))
    rent = Series.of(prorated, [(q1, 9_000.0)], name="Rent")
    doubled = ops.map(rent, fn=lambda v: Na if isna(v) else v * 2, name="Doubled")
    ctx = Context()

    keys = ctx.get(Fn(lambda: keys_until(doubled.cells, q1), name="keys"))
    assert keys == [q1]
    assert ctx.get_at(doubled, q1) == 18_000.0
    # Off-spine queries delegate to the source's own query semantics.
    assert ctx.get_at(doubled, month(1)) == 2 * 9_000.0 * 31 / 90


@pytest.mark.parametrize("effectful", [False, True])
def test_map_is_lazy_and_never_forces_source_cells(effectful: bool):
    def poison() -> float:
        raise AssertionError("source cell was forced")

    def step(day: date) -> tuple[date, Thunk[float], date]:
        return day, Thunk(poison), day + MONTH

    src = Series.unfold(
        exact,
        seed=date(2026, 1, 31),
        step=step,
        name="Src",
    )
    assumption = Fn(poison, name="Assumption")

    def apply(value: Maybe[float]) -> Effect[Maybe[float]]:
        return sum_some(value, (yield from get(assumption)))

    mapped = ops.map(src, fn=apply if effectful else lambda v: v, name="Mapped")

    keys = Context().get(Fn(lambda: keys_until(mapped.cells, date(2026, 3, 1)), name="keys"))
    assert keys == [date(2026, 1, 31), date(2026, 2, 28)]


def test_map_effect_maps_query_answers_and_stored_cells():
    q1 = Period(date(2026, 1, 1), date(2026, 4, 1))
    rent = Series.of(prorated, [(q1, 9_000.0)], name="Rent")
    offset = Val(10.0, name="Offset")

    def apply(value: Maybe[float]) -> Effect[Maybe[float]]:
        return sum_some(value, (yield from get(offset)))

    mapped = ops.map(rent, fn=apply, name="Adjusted")
    ctx = Context()
    # Apply the offset once to each query answer, including off-spine queries.
    assert ctx.get_at(mapped, q1) == 9_010.0
    assert ctx.get_at(mapped, month(1)) == 9_000.0 * 31 / 90 + 10.0
    assert ctx.depends_on((mapped, month(1)), offset)

    node = ctx.get(mapped.cells)
    assert node is not None
    assert node.key == q1
    assert ctx.get(node.value) == 9_010.0
    assert ctx.depends_on(node.value, offset)


def test_map2_maps_generic_values_over_merged_domain():
    d1, d2 = date(2026, 1, 31), date(2026, 2, 28)
    labels = Series.of(exact, [(d1, "revenue")], name="Labels")
    values = Series.of(exact, [(d1, 10), (d2, 20)], name="Values")
    formatted = ops.map2(
        labels,
        values,
        fn=map2_some(lambda label, value: f"{label}: {value}"),
        merge_keys=date_union,
        name="Formatted",
    )
    ctx = Context()

    assert ctx.get_at(formatted, d1) == "revenue: 10"
    assert isna(ctx.get_at(formatted, d2))
    assert ctx.get(Fn(lambda: keys_until(formatted.cells, d2), name="keys")) == [d1, d2]


def test_map2_accepts_effectful_fn():
    d = date(2026, 1, 31)
    left = Series.of(exact, [(d, 10.0)], name="Left")
    right = Series.of(exact, [(d, 20.0)], name="Right")
    factor = Val(2.0, name="Factor")

    def fn(left_value: Maybe[float], right_value: Maybe[float]) -> Effect[float]:
        resolved = yield from get(factor)
        assert not isna(left_value)
        assert not isna(right_value)
        return (left_value + right_value) * resolved

    mapped = ops.map2(left, right, fn=fn, merge_keys=date_union, name="Mapped")
    ctx = Context()

    assert ctx.get_at(mapped, d) == 60.0
    assert ctx.depends_on((mapped, d), factor)


def test_neg():
    d1, d2 = date(2026, 1, 31), date(2026, 2, 28)
    a = Series.of(exact, [(d1, 10.0)], name="A")
    negated = ops.neg(a, name="Neg")
    ctx = Context()

    assert ctx.get_at(negated, d1) == -10.0
    # Na propagates: d2 is an exact miss on the source.
    assert isna(ctx.get_at(negated, d2))


def test_neg_cells_answer_from_spine():
    d = date(2026, 1, 31)
    a = Series.of(exact, [(d, 10.0)], name="A")
    negated = ops.neg(a, name="Neg")
    ctx = Context()

    keys = ctx.get(Fn(lambda: keys_until(negated.cells, d), name="keys"))
    assert keys == [d]

    def first_cell_value() -> Effect[Maybe[float]]:
        node = yield from get(negated.cells)
        assert node is not None
        return (yield from get(node.value))

    assert ctx.get(Fn(first_cell_value, name="first")) == -10.0


def test_scale():
    d1, d2 = date(2026, 1, 31), date(2026, 2, 28)
    source = Series.of(exact, [(d1, 10.0)], name="Source")
    ctx = Context()

    assert ctx.get_at(ops.scale(source, 2.0, name="Scaled"), d1) == 20.0
    assert isna(ctx.get_at(ops.scale(source, 2.0, name="Missing"), d2))


def test_scale_cell_factor_is_lazy_memoized_and_updated_between_contexts():
    d1, d2, d3 = date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)
    source = Series.of(exact, [(d1, 10.0), (d2, 20.0)], name="Source")
    calls = 0

    def compute_factor() -> float:
        nonlocal calls
        calls += 1
        return 2.0

    factor = Fn(compute_factor, name="Factor")
    scaled = ops.scale(source, factor, name="Scaled")
    ctx = Context()
    assert calls == 0
    assert ctx.get(Fn(lambda: keys_until(scaled.cells, d3), name="keys")) == [d1, d2]
    assert calls == 0
    assert ctx.get_at(scaled, d1) == 20.0
    assert ctx.get_at(scaled, d2) == 40.0
    assert isna(ctx.get_at(scaled, d3))
    assert calls == 1
    assert ctx.depends_on((scaled, d1), factor)

    factor._fn = lambda: 3.0
    assert ctx.get_at(scaled, d1) == 20.0
    assert Context().get_at(scaled, d1) == 30.0


def test_scale_accepts_computed_rule_factor():
    d = date(2026, 1, 31)
    source = Series.of(exact, [(d, 10.0)], name="Source")
    assumption = Val(2.0, name="Assumption")

    class Factor(Rule[float]):
        def compute(self) -> Effect[float]:
            return (yield from get(assumption)) + 1.0

    factor = Factor("Factor")
    scaled = ops.scale(source, factor, name="Scaled")
    ctx = Context()
    assert ctx.get_at(scaled, d) == 30.0
    assert ctx.depends_on((scaled, d), factor)
    assert ctx.depends_on((scaled, d), assumption)


def test_merge_cells_standalone_plain_values():
    d1, d2 = date(2026, 1, 31), date(2026, 2, 28)
    a = Series.of(exact, [(d1, 0.0)], name="A")
    b = Series.of(exact, [(d2, 0.0)], name="B")
    merged = Series(
        merge_cells([a.cells, b.cells], date_union, lambda k: float(k.month), name="Merged"),
        exact,
        name="Merged",
    )
    ctx = Context()

    assert ctx.get_at(merged, d1) == 1.0
    assert ctx.get_at(merged, d2) == 2.0
