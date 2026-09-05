from datetime import date
from typing import Any

import pytest
from dateutil.relativedelta import relativedelta

from orcaset import (
    YF,
    Cell,
    Cells,
    Cons,
    Context,
    Effect,
    Key,
    Maybe,
    Na,
    Period,
    QueryFn,
    Series,
    Thunk,
    accrue,
    continue_series,
    covered,
    date_split,
    exact,
    get,
    get_at,
    isna,
    keys_until,
    last,
    ops,
    period_split,
    unfold_cells,
)

MONTH = relativedelta(months=1)
Q1 = Period(date(2025, 1, 1), date(2025, 4, 1))
Q2 = Period(date(2025, 4, 1), date(2025, 7, 1))
Q3 = Period(date(2025, 7, 1), date(2025, 10, 1))
OCT = Period(date(2025, 10, 1), date(2025, 11, 1))
NOV = Period(date(2025, 11, 1), date(2025, 12, 1))
DEC = Period(date(2025, 12, 1), date(2026, 1, 1))
YEAR = Period(Q1.start, DEC.end)
accrue_monthly = accrue(YF.cmonthly)

type Amounts = Series[Period, Any, Maybe[float]]
type AmountQuery = QueryFn[Period, Maybe[float], Maybe[float]]


def components[K: Key, W](*sources: Series[K, Any, W]) -> Cells[int, Series[K, Any, W]]:
    return Series.of("components", exact, enumerate(sources)).cells


def joined(*sources: Amounts, query: AmountQuery = covered) -> Amounts:
    return Series.flatten("joined", components(*sources), query=query, split_keys=period_split)


def monthly(name: str, start: Period, value: float) -> Series[Period, float, Maybe[float]]:
    return Series.unfold(
        name, accrue_monthly, seed=start, step=lambda p: (p, value, p.from_end(MONTH))
    )


@pytest.mark.parametrize(
    ("q", "key", "expected"),
    [
        (Q1, Q1, (Q1, None)),
        (Q1, Q3, (Q1, None)),
        (OCT, Q3, (None, OCT)),
        (Period(Q3.start, NOV.end), Q3, (Q3, Period(OCT.start, NOV.end))),
        (YEAR, Q3, (Period(Q1.start, Q3.end), Period(OCT.start, DEC.end))),
    ],
)
def test_period_split(q: Period, key: Period, expected: tuple[Period | None, Period | None]):
    assert period_split(q, key) == expected


def test_components_keep_their_own_queries():
    actuals = Series.of("actuals", covered, [(Q1, 300.0), (Q2, 330.0), (Q3, 363.0)])
    revenue = joined(actuals, monthly("forecast", OCT, 100.0))
    ctx = Context()
    assert ctx.get_at(revenue, Q2) == 330.0
    assert ctx.get_at(revenue, Period(Q1.start, Q3.end)) == 993.0
    assert isna(ctx.get_at(revenue, Period(date(2025, 9, 1), Q3.end)))
    half = Period(OCT.start, date(2025, 10, 16))
    assert ctx.get_at(revenue, half) == pytest.approx(
        100.0 * YF.cmonthly(*half) / YF.cmonthly(*OCT)
    )
    assert ctx.get_at(revenue, Period(Q3.start, NOV.end)) == 563.0
    assert ctx.get_at(revenue, YEAR) == 1293.0
    assert isna(ctx.get_at(revenue, Period(date(2025, 9, 1), NOV.end)))


def test_single_component_delegates_on_and_off_spine_without_outer_fold():
    def poison_query(q: Period, cells: Cells[Period, Maybe[float]]) -> Maybe[float]:
        raise AssertionError("outer fold is only for crossing or empty queries")

    source = Series.of("source", accrue_monthly, [(Q3, 300.0)])
    revenue = joined(source, query=poison_query)
    ctx = Context()
    for q in (Q3, OCT, Period(Q3.start, NOV.end), YEAR):
        assert ctx.get_at(revenue, q) == ctx.get_at(source, q)


def test_derived_continuation_contributes_its_answer_and_preserves_dependencies():
    actuals = Series.of("actuals", covered, [(Q3, 363.0)])
    forecast = ops.scale("scaled forecast", monthly("forecast", OCT, 100.0), 2.0)
    revenue = joined(actuals, forecast)
    crossing = Period(Q3.start, NOV.end)
    ctx = Context()
    assert ctx.get_at(revenue, crossing) == 763.0
    deps = ctx.dependencies(revenue, crossing).deps
    assert {(node.name, node.key) for node in deps} == {
        ("actuals", Q3),
        ("scaled forecast", Period(OCT.start, NOV.end)),
    }


def test_straddling_continuation_is_clipped_and_queried_on_the_remainder():
    actuals = Series.of("actuals", covered, [(Q3, 363.0)])
    annual_forecast = Series.of("annual forecast", accrue_monthly, [(YEAR, 1200.0)])
    revenue = joined(actuals, annual_forecast)
    q4 = Period(OCT.start, DEC.end)
    ctx = Context()
    assert ctx.get_at(revenue, Period(OCT.start, NOV.end)) == 200.0
    assert ctx.get_at(revenue, Period(Q3.start, NOV.end)) == 563.0
    assert ctx.get(Cell("keys", lambda: keys_until(revenue.cells, q4))) == [Q3, q4]
    node = ctx.get(revenue.cells)
    assert node is not None
    clipped = ctx.get(node.tail)
    assert clipped is not None and clipped.key == q4
    assert ctx.get(clipped.cell) == ctx.get_at(revenue, q4) == 300.0


def test_clipping_does_not_interpolate_a_component_that_forbids_it():
    actuals = Series.of("actuals", covered, [(Q3, 363.0)])
    forecast = Series.of("forecast", covered, [(YEAR, 1200.0)])
    revenue = joined(actuals, forecast)
    assert isna(Context().get_at(revenue, Period(OCT.start, DEC.end)))
    assert isna(Context().get_at(revenue, Period(Q3.start, DEC.end)))


def test_flatten_composes_as_either_a_base_or_a_continuation():
    a = Series.of("a", covered, [(Q1, 1.0)])
    b = Series.of("b", covered, [(Q2, 2.0)])
    c = Series.of("c", covered, [(Q3, 3.0)])
    alternatives = (joined(a, b, c), joined(joined(a, b), c), joined(a, joined(b, c)))
    for revenue in alternatives:
        ctx = Context()
        assert ctx.get_at(revenue, Period(Q1.start, Q2.end)) == 3.0
        assert ctx.get_at(revenue, Period(Q1.start, Q3.end)) == 6.0
        assert ctx.get_at(revenue, Period(Q2.start, Q3.end)) == 5.0
        assert isna(ctx.get_at(revenue, Period(date(2025, 2, 1), Q3.end)))
        assert ctx.get(Cell("keys", lambda s=revenue: keys_until(s.cells, Q3))) == [Q1, Q2, Q3]


def test_empty_and_fully_clipped_components_do_not_create_seams():
    empty: Amounts = Series.of("empty", exact, [])
    a = Series.of("a", covered, [(Q1, 1.0)])
    clipped = Series.of("clipped", exact, [(Q1, Thunk(poison))])
    b = Series.of("b", covered, [(Q2, 2.0)])
    revenue = joined(empty, a, empty, clipped, b, empty)
    ctx = Context()
    assert ctx.get_at(revenue, Period(Q1.start, Q2.end)) == 3.0
    assert ctx.get(Cell("keys", lambda: keys_until(revenue.cells, Q3))) == [Q1, Q2]
    assert isna(ctx.get_at(joined(empty, empty), Q1))
    outer: Cells[int, Amounts] = components()
    assert isna(
        ctx.get_at(Series.flatten("empty", outer, query=covered, split_keys=period_split), Q1)
    )


def poison() -> float:
    raise AssertionError("unneeded component value was read")


def test_keys_and_rejected_crossing_queries_do_not_read_values():
    a = Series.of("a", covered, [(Q1, Thunk(poison)), (Q2, Thunk(poison))])
    b = Series.of("b", accrue_monthly, [(Q1, Thunk(poison)), (Q3, Thunk(poison))])
    revenue = joined(a, b, query=exact)
    ctx = Context()
    assert ctx.get(Cell("keys", lambda: keys_until(revenue.cells, Q3))) == [Q1, Q2, Q3]
    assert isna(ctx.get_at(revenue, Period(Q2.start, Q3.end)))


def test_stitch_can_short_circuit_before_reading_later_component_values():
    a = Series.of("a", covered, [(Q1, Na)])
    b = Series.of("b", covered, [(Q2, Thunk(poison))])
    assert isna(Context().get_at(joined(a, b), Period(Q1.start, Q2.end)))


@pytest.mark.parametrize("forecast_query", [covered, accrue_monthly])
def test_a_gap_after_the_seam_belongs_to_the_next_component(forecast_query: AmountQuery):
    a = Series.of("a", covered, [(Q3, 300.0)])
    b = Series.of("b", forecast_query, [(NOV, 100.0)])
    revenue = joined(a, b)
    ctx = Context()
    assert isna(ctx.get_at(revenue, OCT))
    crossing = Period(Q3.start, NOV.end)
    if forecast_query is covered:
        assert isna(ctx.get_at(revenue, crossing))
    else:
        # The outer fold preserves the source's policy for missing coverage.
        assert ctx.get_at(revenue, crossing) == 400.0


def test_date_routing_preserves_exact_last_and_final_carry_forward():
    d0, d1, d2, d3 = (date(2025, m, 1) for m in (1, 2, 3, 4))
    assert date_split(d0, d1) == (d0, None)
    assert date_split(d1, d1) == (d1, None)
    assert date_split(d2, d1) == (None, d2)
    a = Series.of("a", exact, [(d0, 1.0), (d1, 2.0)])
    b = Series.of("b", last, [(d1, 99.0), (d2, 3.0)])
    revenue = Series.flatten("revenue", components(a, b), query=exact, split_keys=date_split)
    ctx = Context()
    assert ctx.get_at(revenue, d1) == 2.0
    assert isna(ctx.get_at(revenue, date(2025, 1, 15)))
    # Delegation on a post-seam gap retains the continuation's last policy.
    assert ctx.get_at(revenue, date(2025, 2, 15)) == 99.0
    assert ctx.get_at(revenue, d2) == ctx.get_at(revenue, d3) == 3.0
    assert ctx.get(Cell("keys", lambda: keys_until(revenue.cells, d3))) == [d0, d1, d2]


def int_split(q: int, k: int) -> tuple[int | None, int | None]:
    return (q, None) if q <= k else (None, q)


def test_infinite_base_does_not_force_outer_tail_or_treat_na_as_exhaustion():
    visited: list[int] = []

    def step(i: int) -> tuple[int, Maybe[float], int]:
        assert i < 10, "attempted to exhaust an infinite base"
        visited.append(i)
        return i, Na if i == 3 else float(i), i + 1

    def forbidden(last_node: Cons[int, Maybe[float]] | None) -> Series[int, float, Maybe[float]]:
        raise AssertionError("infinite base constructed a continuation")

    base = Series.unfold("base", exact, seed=0, step=step)
    chain = continue_series("components", base, forbidden)
    revenue = Series.flatten("revenue", chain, query=exact, split_keys=int_split)
    ctx = Context()
    assert ctx.get(chain) is not None
    assert visited == []
    assert ctx.get_at(revenue, 2) == 2.0
    assert visited == [0, 1, 2]
    assert isna(ctx.get_at(revenue, 3))
    assert ctx.get_at(revenue, 5) == 5.0
    assert visited == list(range(6))
    assert ctx.get(Cell("keys", lambda: keys_until(revenue.cells, 5))) == list(range(6))
    assert visited == list(range(7))  # keys_until's ordinary one-node lookahead


def test_query_endpoint_does_not_peek_into_base_tail_or_next_component():
    def forbidden_tail() -> Cons[Period, float] | None:
        raise AssertionError("query forced its endpoint's tail")

    base = Series(
        "base",
        Cell("head", lambda: Cons(Q1, Cell("value", lambda: 10.0), Cell("tail", forbidden_tail))),
        exact,
    )
    revenue = joined(base, monthly("forecast", Q2, 100.0))
    assert Context().get_at(revenue, Q1) == 10.0


def test_infinite_outer_chain_is_also_lazy():
    constructed: list[int] = []

    def step(i: int) -> tuple[int, Series[int, float, Maybe[float]], int]:
        assert i < 5, "attempted to materialize all components"
        constructed.append(i)
        return i, Series.of(f"component {i}", exact, [(i, float(i))]), i + 1

    outer = unfold_cells("components", seed=0, step=step)
    revenue = Series.flatten("revenue", outer, query=exact, split_keys=int_split)
    assert Context().get_at(revenue, 2) == 2.0
    assert constructed == [0, 1, 2]


def test_finite_base_builds_terminal_growth_once_per_context_from_last_raw_node():
    forced: list[str] = []
    calls: list[Cons[Period, float] | None] = []

    def initial() -> float:
        forced.append("last projection")
        return 100.0

    base = Series.of("projections", exact, [(OCT, Thunk(poison)), (NOV, Thunk(initial))])

    def terminal(
        last_node: Cons[Period, float] | None,
    ) -> Series[Period, Maybe[float], Maybe[float]]:
        calls.append(last_node)
        assert last_node is not None
        first = last_node.key.from_end(MONTH)

        @Series.define("terminal growth", accrue_monthly, seed=first)
        def forecast(p: Period) -> tuple[Period, Thunk[Maybe[float]], Period]:
            def value() -> Effect[Maybe[float]]:
                prior = (
                    (yield from get(last_node.cell))
                    if p == first
                    else (yield from get_at(forecast, p.from_start(-MONTH)))
                )
                return Na if isna(prior) else prior * 1.1

            return p, Thunk(value), p.from_end(MONTH)

        return forecast

    revenue = Series.flatten(
        "revenue",
        continue_series("components", base, terminal),
        query=covered,
        split_keys=period_split,
    )
    ctx = Context()
    assert ctx.get_at(revenue, NOV) == 100.0
    assert calls == []
    jan = DEC.from_end(MONTH)
    assert ctx.get_at(revenue, jan) == pytest.approx(121.0)
    assert ctx.get_at(revenue, DEC) == pytest.approx(110.0)
    assert forced == ["last projection"]
    assert len(calls) == 1 and calls[0] is not None and calls[0].key == NOV
    assert Context().get_at(revenue, DEC) == pytest.approx(110.0)
    assert len(calls) == 2 and forced == ["last projection", "last projection"]


def test_continue_an_empty_base():
    base: Series[Period, float, Maybe[float]] = Series.of("empty", exact, [])
    calls: list[Cons[Period, float] | None] = []

    def terminal(last_node: Cons[Period, float] | None) -> Series[Period, float, Maybe[float]]:
        calls.append(last_node)
        return monthly("terminal", OCT, 100.0)

    revenue = Series.flatten(
        "revenue",
        continue_series("components", base, terminal),
        query=covered,
        split_keys=period_split,
    )
    assert Context().get_at(revenue, OCT) == 100.0
    assert calls == [None]


def test_base_domain_can_depend_on_the_composed_series_at_its_previous_key():
    def step(i: int) -> Effect[tuple[int, float, int] | None]:
        if i:
            previous = yield from get_at(revenue, i - 1)
            if not isna(previous) and previous >= 2.0:
                return None
        return i, float(i + 1), i + 1

    def terminal(last_node: Cons[int, float] | None) -> Series[int, float, Maybe[float]]:
        assert last_node is not None
        return Series.unfold(
            "terminal", exact, seed=last_node.key + 1, step=lambda k: (k, 100.0, k + 1)
        )

    base = Series.unfold("base", exact, seed=0, step=step)
    revenue: Series[int, Maybe[float], Maybe[float]] = Series.flatten(
        "revenue",
        continue_series("components", base, terminal),
        query=exact,
        split_keys=int_split,
    )
    ctx = Context()
    assert [ctx.get_at(revenue, k) for k in range(4)] == [1.0, 2.0, 100.0, 100.0]


def test_raw_cell_types_can_differ_without_changing_answer_type():
    def text_amount(q: Period, cells: Cells[Period, str]) -> Effect[Maybe[float]]:
        value = yield from exact(q, cells)
        return Na if isna(value) else float(value)

    a = Series.of("text amounts", text_amount, [(Q1, "100")])
    b = Series.of("float amounts", covered, [(Q2, 200.0)])
    assert Context().get_at(joined(a, b), Period(Q1.start, Q2.end)) == 300.0


def test_non_numeric_answers_use_an_explicit_crossing_fold():
    def concatenate(q: Period, cells: Cells[Period, Maybe[str]]) -> Effect[Maybe[str]]:
        values: list[str] = []
        node = yield from get(cells)
        while node is not None:
            value = yield from get(node.cell)
            if isna(value):
                return Na
            values.append(value)
            node = yield from get(node.tail)
        return "/".join(values)

    a = Series.of("a", exact, [(Q1, "actual")])
    b = Series.of("b", exact, [(Q2, "forecast")])
    series = Series.flatten("labels", components(a, b), query=concatenate, split_keys=period_split)
    assert Context().get_at(series, Period(Q1.start, Q2.end)) == "actual/forecast"
