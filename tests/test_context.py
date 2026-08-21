from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from math import isclose

import pytest
from dateutil.relativedelta import relativedelta

from orcaset import (
    CellFactory,
    Context,
    ConvergenceError,
    CycleError,
    DateSeries,
    Iterate,
    KeyedRuleBase,
    Period,
    PeriodSeries,
    RuleBase,
    Step,
    abs_distance,
    exact_or,
    get,
    get_at,
    maybe_abs_distance,
)
from orcaset.maybe import Maybe, Na, isna
from orcaset.rule import _MISSING, _iterate


class Const(RuleBase[float]):
    def __init__(self, name: str, value: float) -> None:
        super().__init__(name)
        self._value = value

    def compute(self) -> float:
        return self._value


class SelfFixedPoint(RuleBase[float]):
    """x = 0.5 * x + 1, whose unique fixed point is 2."""

    def compute(self) -> Step[float]:
        prior = yield from get(self, seed=1.0, distance=abs_distance)
        return 0.5 * prior + 1.0


class SelfCycle(RuleBase[float]):
    def compute(self) -> Step[float]:
        prior = yield from get(self)
        return prior + 1.0


class Divergent(RuleBase[float]):
    def compute(self) -> Step[float]:
        prior = yield from get(self, seed=1.0, distance=abs_distance, max_iter=8)
        return prior + 1.0


@dataclass(frozen=True, slots=True)
class USD:
    amount: float


def usd_distance(a: USD, b: USD) -> float:
    return abs(a.amount - b.amount)


class UsdFixedPoint(RuleBase[USD]):
    def compute(self) -> Step[USD]:
        prior = yield from get(self, seed=USD(0.0), distance=usd_distance)
        return USD(0.5 * prior.amount + 1.0)


class Interest(KeyedRuleBase[int, float]):
    def __init__(self, rate: float) -> None:
        super().__init__("interest")
        self._rate = rate
        self.debt: KeyedRuleBase[int, float] | None = None

    def compute(self, period: int, /) -> Step[float]:
        debt = self.debt
        if debt is None:
            raise RuntimeError("interest.debt was not wired")
        end = yield from get_at(debt, period, seed=0.0, distance=abs_distance)
        begin = 100.0
        return self._rate * 0.5 * (begin + end)


class EndingDebt(KeyedRuleBase[int, float]):
    def __init__(self) -> None:
        super().__init__("ending_debt")
        self.interest: Interest | None = None

    def compute(self, period: int, /) -> Step[float]:
        interest = self.interest
        if interest is None:
            raise RuntimeError("ending_debt.interest was not wired")
        amount = yield from get_at(interest, period)
        return 100.0 + amount


class SeededEndingDebt(KeyedRuleBase[int, float]):
    def __init__(self) -> None:
        super().__init__("ending_debt")
        self.interest: Interest | None = None

    def compute(self, period: int, /) -> Step[float]:
        interest = self.interest
        if interest is None:
            raise RuntimeError("ending_debt.interest was not wired")
        amount = yield from get_at(interest, period, seed=0.0, distance=abs_distance)
        return 100.0 + amount


def test_acyclic_demand_is_unchanged():
    src = Const("src", 10.0)
    ctx = Context()
    assert ctx.get(src) == 10.0
    assert ctx.rule_dependencies(src).value == 10.0


def test_seed_is_ignored_when_there_is_no_cycle():
    src = Const("src", 10.0)

    class Reader(RuleBase[float]):
        def compute(self) -> Step[float]:
            return (yield from get(src, seed=0.0, distance=abs_distance))

    ctx = Context()
    assert ctx.get(Reader("reader")) == 10.0


def test_cycle_without_iterate_raises():
    rule = SelfCycle("loop")
    ctx = Context()
    with pytest.raises(CycleError, match="Demand cycle: loop"):
        ctx.get(rule)


def test_self_cycle_converges_to_fixed_point():
    rule = SelfFixedPoint("x")
    ctx = Context()
    assert isclose(ctx.get(rule), 2.0)


def test_self_cycle_is_memoized_after_convergence():
    rule = SelfFixedPoint("x")
    ctx = Context()
    first = ctx.get(rule)
    second = ctx.get(rule)
    assert first == second
    assert isclose(first, 2.0)


def test_non_converging_cycle_raises():
    rule = Divergent("grow")
    ctx = Context()
    with pytest.raises(ConvergenceError, match="Failed to converge grow after 8") as caught:
        ctx.get(rule)
    err = caught.value
    assert err.values == (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0)
    assert err.residuals == (1.0,) * 8
    assert "  0: 1.0" in str(err)
    assert "  8: 9.0  distance=1.0" in str(err)


def test_oscillation_is_visible_on_convergence_error():
    class Flip(RuleBase[float]):
        def compute(self) -> Step[float]:
            prior = yield from get(self, seed=0.0, distance=abs_distance, max_iter=4)
            return 1.0 - prior

    ctx = Context()
    with pytest.raises(ConvergenceError) as caught:
        ctx.get(Flip("flip"))
    assert caught.value.values == (0.0, 1.0, 0.0, 1.0, 0.0)


def test_two_node_average_balance_interest():
    # end = begin + rate * (begin + end) / 2
    # end = begin * (1 + r/2) / (1 - r/2)
    rate = 0.10
    interest = Interest(rate)
    debt = EndingDebt()
    interest.debt = debt
    debt.interest = interest

    ctx = Context()
    end = ctx.get_at(debt, 0)
    expected = 100.0 * (1 + rate / 2) / (1 - rate / 2)
    assert isclose(end, expected, rel_tol=1e-9)
    assert isclose(ctx.get_at(interest, 0), end - 100.0, rel_tol=1e-9)


@pytest.mark.parametrize("enter", ["debt", "interest"])
def test_seed_on_both_cycle_edges_converges_from_either_entry(enter: str):
    rate = 0.10
    interest = Interest(rate)
    debt = SeededEndingDebt()
    interest.debt = debt
    debt.interest = interest

    ctx = Context()
    if enter == "debt":
        end = ctx.get_at(debt, 0)
        amount = ctx.get_at(interest, 0)
    else:
        amount = ctx.get_at(interest, 0)
        end = ctx.get_at(debt, 0)

    expected_end = 100.0 * (1 + rate / 2) / (1 - rate / 2)
    assert isclose(end, expected_end, rel_tol=1e-9)
    assert isclose(amount, expected_end - 100.0, rel_tol=1e-9)


def test_pending_spec_seeds_back_edge_to_the_started_cell():
    """Seed on the demand that starts a cyclic cell covers a later back-edge."""

    class Root(RuleBase[float]):
        def compute(self) -> Step[float]:
            return (yield from get(loop, seed=0.0, distance=abs_distance))

    class Loop(RuleBase[float]):
        def compute(self) -> Step[float]:
            prior = yield from get(self)
            return 0.5 * prior + 1.0

    loop = Loop("loop")
    ctx = Context()
    assert isclose(ctx.get(Root("root")), 2.0)


def test_custom_value_type_uses_typed_seed_and_distance():
    ctx = Context()
    value = ctx.get(UsdFixedPoint("usd"))
    assert isclose(value.amount, 2.0)


def test_maybe_distance_treats_na_mismatch_as_infinite():
    assert maybe_abs_distance(Na, Na) == 0.0
    assert maybe_abs_distance(1.0, Na) == float("inf")
    assert maybe_abs_distance(1.0, 4.0) == 3.0


def test_maybe_cycle_with_maybe_abs_distance():
    class Loop(RuleBase[Maybe[float]]):
        def compute(self) -> Step[Maybe[float]]:
            prior = yield from get(self, seed=0.0, distance=maybe_abs_distance)
            if isna(prior):
                return 1.0
            return 0.25 * prior + 3.0

    ctx = Context()
    # x = 0.25 x + 3 => x = 4
    assert ctx.get(Loop("m")) == pytest.approx(4.0)


def test_seed_without_distance_raises():
    with pytest.raises(TypeError, match="seed and distance must be provided together"):
        _iterate(0.0, _MISSING, None, None)


def test_per_demand_tol_overrides_context():
    class Loop(RuleBase[float]):
        def compute(self) -> Step[float]:
            prior = yield from get(self, seed=0.0, distance=abs_distance, tol=1e-12)
            return 0.5 * prior + 1.0

    ctx = Context(tol=1.0)
    assert isclose(ctx.get(Loop("x")), 2.0)


def test_context_max_iter_default_is_used():
    class Grow(RuleBase[float]):
        def compute(self) -> Step[float]:
            prior = yield from get(self, seed=1.0, distance=abs_distance)
            return prior + 1.0

    ctx = Context(max_iter=3)
    with pytest.raises(ConvergenceError, match="after 3 iterations") as caught:
        ctx.get(Grow("grow"))
    assert caught.value.values == (1.0, 2.0, 3.0, 4.0)


def test_long_iterate_history_omits_the_middle_of_the_message():
    class Grow(RuleBase[float]):
        def compute(self) -> Step[float]:
            prior = yield from get(self, seed=0.0, distance=abs_distance, max_iter=25)
            return prior + 1.0

    ctx = Context()
    with pytest.raises(ConvergenceError) as caught:
        ctx.get(Grow("grow"))
    err = caught.value
    assert err.values[0] == 0.0
    assert err.values[-1] == 25.0
    assert len(err.values) == 26
    text = str(err)
    assert "iterates omitted" in text
    assert "  0: 0.0" in text
    assert "  25: 25.0  distance=1.0" in text


def test_dependencies_include_cyclic_edge_after_solve():
    rule = SelfFixedPoint("x")
    ctx = Context()
    tree = ctx.rule_dependencies(rule)
    assert tree.name == "x"
    assert isclose(tree.value, 2.0)
    assert len(tree.deps) == 1
    assert tree.deps[0].name == "x"


def test_iterate_dataclass_matches_get_kwargs():
    spec = Iterate(seed=0.0, distance=abs_distance, tol=1e-6, max_iter=10)
    assert spec.seed == 0.0
    assert spec.distance(1.0, 4.0) == 3.0
    assert spec.tol == 1e-6
    assert spec.max_iter == 10


@pytest.mark.parametrize("enter", ["a", "b", "c"])
def test_one_seed_solves_three_node_cycle_from_any_entry(enter: str):
    class A(RuleBase[float]):
        def compute(self) -> Step[float]:
            return (yield from get(b))

    class B(RuleBase[float]):
        def compute(self) -> Step[float]:
            prior = yield from get(c, seed=0.0, distance=abs_distance)
            return 0.5 * prior + 1.0

    class C(RuleBase[float]):
        def compute(self) -> Step[float]:
            return (yield from get(a))

    a = A("a")
    b = B("b")
    c = C("c")
    ctx = Context()
    start = {"a": a, "b": b, "c": c}[enter]
    assert isclose(ctx.get(start), 2.0)
    assert isclose(ctx.get(a), 2.0)
    assert isclose(ctx.get(b), 2.0)
    assert isclose(ctx.get(c), 2.0)


def test_joint_residuals_keep_iterating_when_cut_tol_is_loose():
    class A(RuleBase[float]):
        def compute(self) -> Step[float]:
            other = yield from get(b, seed=0.0, distance=abs_distance, tol=1e-12)
            return 0.5 * other + 1.0

    class B(RuleBase[float]):
        def compute(self) -> Step[float]:
            other = yield from get(a, seed=0.0, distance=abs_distance, tol=1.0)
            return 0.5 * other + 1.0

    a = A("a")
    b = B("b")
    ctx = Context()
    # Entering through A, the back-edge is B→A with loose tol=1. B's tight
    # spec must still be satisfied, otherwise iteration would stop around 1.875.
    value = ctx.get(a)
    assert isclose(value, 2.0, abs_tol=1e-9)
    assert isclose(ctx.get(b), 2.0, abs_tol=1e-9)


def test_freeze_recomputes_dependents_from_committed_cut():
    class A(RuleBase[float]):
        def compute(self) -> Step[float]:
            other = yield from get(b)
            return 0.5 * other + 1.0

    class B(RuleBase[float]):
        def compute(self) -> Step[float]:
            other = yield from get(a, seed=0.0, distance=abs_distance, tol=0.1)
            return 0.5 * other + 1.0

    a = A("a")
    b = B("b")
    ctx = Context()
    end = ctx.get(a)
    other = ctx.get(b)
    assert other == 0.5 * end + 1.0


def test_nested_independent_cycles_each_need_a_seed():
    class Inner(RuleBase[float]):
        def compute(self) -> Step[float]:
            prior = yield from get(self, seed=1.0, distance=abs_distance)
            return 0.5 * prior + 1.0

    inner = Inner("inner")

    class Outer(RuleBase[float]):
        def compute(self) -> Step[float]:
            inner_val = yield from get(inner)
            prior = yield from get(self, seed=0.0, distance=abs_distance)
            return 0.5 * prior + inner_val

    ctx = Context()
    assert isclose(ctx.get(Outer("outer")), 4.0)
    assert isclose(ctx.get(inner), 2.0)


def test_seeded_cell_behind_dropped_branch_does_not_block():
    """A sweep/trigger seed that stops being demanded must not stall the solve."""

    class Side(RuleBase[float]):
        def compute(self) -> Step[float]:
            return (yield from get(loop))

    side = Side("side")

    class Loop(RuleBase[float]):
        def compute(self) -> Step[float]:
            prior = yield from get(self, seed=0.0, distance=abs_distance)
            if prior < 1.9:
                extra = yield from get(side, seed=0.0, distance=abs_distance)
                return 0.5 * prior + 1.0 + 0.0 * extra
            return 0.5 * prior + 1.0

    loop = Loop("loop")
    ctx = Context()
    assert isclose(ctx.get(loop), 2.0)


def test_convergence_error_names_unobserved_seeded_cell():
    class Side(RuleBase[float]):
        def compute(self) -> Step[float]:
            return (yield from get(loop))

    side = Side("side")

    class Loop(RuleBase[float]):
        def compute(self) -> Step[float]:
            prior = yield from get(self, seed=0.0, distance=abs_distance, max_iter=3)
            if prior == 0.0:
                extra = yield from get(side, seed=0.0, distance=abs_distance)
                return 0.5 * prior + 1.0 + 0.0 * extra
            return prior + 1.0

    loop = Loop("loop")
    ctx = Context()
    with pytest.raises(ConvergenceError) as caught:
        ctx.get(loop)
    err = caught.value
    assert err.unobserved
    assert "side" in str(err)
    assert "not observed this iteration" in str(err)


def test_composed_series_cycle_with_one_seed_from_either_entry():
    start = date(2022, 12, 31)
    period = next(Period.seq(start, relativedelta(years=1, day=31)))
    opening = 100.0
    ebitda_amt = 20.0
    rate = 0.10

    def require(value: Maybe[float]) -> float:
        if isna(value):
            raise AssertionError("expected a float, got Na")
        return value

    ebitda = PeriodSeries("EBITDA", lambda: ((period, ebitda_amt),), exact_or(0.0))

    def interest_cells() -> Iterator[tuple[Period, CellFactory[float]]]:
        def factory() -> Step[float]:
            end = yield from get_at(debt, period.end, seed=0.0, distance=abs_distance)
            return -rate * (opening + end) / 2.0

        yield period, factory

    interest = PeriodSeries("Interest", interest_cells, exact_or(0.0))
    fcf = (ebitda + interest).named("FCF")

    def debt_cells() -> Iterator[tuple[date, float | CellFactory[float]]]:
        yield start, opening

        def factory() -> Step[float]:
            fcf_val = require((yield from get_at(fcf, period)))
            return opening - fcf_val

        yield period.end, factory

    debt = DateSeries("Debt", debt_cells, exact_or(0.0))
    # ending = opening - ebitda + rate * (opening + ending) / 2
    expected_end = (opening * (1.0 + rate / 2.0) - ebitda_amt) / (1.0 - rate / 2.0)

    def assert_solved(ctx: Context) -> None:
        end = ctx.get_at(debt, period.end)
        flow = require(ctx.get_at(fcf, period))
        amount = ctx.get_at(interest, period)
        assert isclose(end, expected_end, rel_tol=1e-9)
        assert isclose(flow, opening - end, rel_tol=1e-9)
        assert isclose(amount, flow - ebitda_amt, rel_tol=1e-9)

    ctx_fcf = Context()
    ctx_fcf.get_at(fcf, period)
    assert_solved(ctx_fcf)
    ctx_debt = Context()
    ctx_debt.get_at(debt, period.end)
    assert_solved(ctx_debt)


def test_period_and_date_series_circular_interest():
    start = date(2025, 12, 31)
    month = relativedelta(months=1, day=31)
    period = next(Period.seq(start, month))
    rate = 0.10

    debt: DateSeries[float]
    interest: PeriodSeries[float]

    def debt_cells() -> Iterator[tuple[date, float | CellFactory[float]]]:
        yield start, 100.0

        def factory() -> Step[float]:
            begin = yield from get_at(debt, start)
            amount = yield from get_at(interest, period)
            return begin + amount

        yield period.end, factory

    def interest_cells() -> Iterator[tuple[Period, CellFactory[float]]]:
        def factory() -> Step[float]:
            begin = yield from get_at(debt, period.start)
            end = yield from get_at(debt, period.end, seed=0.0, distance=abs_distance)
            return rate * 0.5 * (begin + end)

        yield period, factory

    debt = DateSeries("Debt", debt_cells, exact_or(0.0))
    interest = PeriodSeries("Interest", interest_cells, exact_or(0.0))

    ctx = Context()
    end = ctx.get_at(debt, period.end)
    expected = 100.0 * (1 + rate / 2) / (1 - rate / 2)
    assert isclose(end, expected, rel_tol=1e-9)
    assert isclose(ctx.get_at(interest, period), end - 100.0, rel_tol=1e-9)
