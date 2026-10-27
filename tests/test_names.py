from datetime import date

import pytest

from orcaset import (
    Context,
    Effect,
    Fn,
    KeyedFn,
    Period,
    Rule,
    Series,
    Val,
    clip_periods,
    date_union,
    get,
    ops,
    period_union,
    stmt,
)
from orcaset.query import exact
from orcaset.rule import AutoName

D1 = date(2026, 1, 31)


def test_explicit_names_are_kept_and_marked_named():
    a = Series.of(exact, [(D1, 1.0)], name="A")
    assert a.name == "A"
    assert a.named
    assert not isinstance(a.name, AutoName)


def test_ops_derive_names_from_operands():
    a = Series.of(exact, [(D1, 1.0)], name="A")
    b = Series.of(exact, [(D1, 2.0)], name="B")
    rate = Val(0.3, name="Rate")

    assert ops.add(a, b, merge_keys=date_union).name == "add(A, B)"
    assert ops.sub(a, b, merge_keys=date_union).name == "sub(A, B)"
    assert ops.neg(a).name == "neg(A)"
    assert ops.scale(a, 0.3).name == "scale(A, 0.3)"
    assert ops.scale(a, rate).name == "scale(A, Rate)"
    assert ops.map(a, fn=lambda value: value).name == "map(A)"
    assert not ops.add(a, b, merge_keys=date_union).named


def test_nested_derived_names_collapse():
    a = Series.of(exact, [(D1, 1.0)], name="A")
    b = Series.of(exact, [(D1, 2.0)], name="B")
    total = ops.add(a, b, merge_keys=date_union)
    assert ops.sub(total, a, merge_keys=date_union).name == "sub(add(…), A)"


def test_leaf_and_decorator_defaults():
    def growth() -> float:
        return 0.05

    @Fn.define
    def contingent_rate() -> float:
        return 0.1

    @KeyedFn.define
    def doubled(key: int) -> int:
        return key * 2

    @Series.define(exact, seed=0)
    def revenue(state: int) -> tuple[date, float, int] | None:
        return None

    assert Fn(growth).name == "growth"
    assert contingent_rate.name == "contingent_rate"
    assert doubled.name == "doubled"
    assert revenue.name == "revenue"
    assert not revenue.named
    assert Val(0.05).name == "0.05"
    assert Val("x" * 100).name.endswith("…")
    assert len(Val("x" * 100).name) == 24


def test_fallback_names_use_kind_and_id():
    lam = Fn(lambda: 1.0)
    assert lam.name == f"Fn#{lam.id}"
    assert Series.of(exact, [(D1, 1.0)]).name.startswith("Series#")


def test_explicit_decorator_name_wins():
    @Fn.define(name="Contingent rate")
    def contingent_rate() -> float:
        return 0.1

    assert contingent_rate.name == "Contingent rate"
    assert contingent_rate.named


def test_default_name_hook_is_lazy():
    class Scaled(Rule[float]):
        def __init__(self, source: Rule[float], factor: float) -> None:
            super().__init__()
            self.source = source
            self.factor = factor

        def default_name(self) -> str:
            return f"{self.source.name}×{self.factor}"

        def compute(self) -> Effect[float]:
            return (yield from get(self.source)) * self.factor

    scaled = Scaled(Val(2.0, name="Base"), 3.0)
    assert scaled.name == "Base×3.0"
    assert not scaled.named
    assert Context().get(scaled) == 6.0


def test_reading_names_never_evaluates_rules():
    calls: list[str] = []

    def boom(label: str) -> float:
        calls.append(label)
        raise AssertionError(f"{label} evaluated while reading names")

    def step(state: int) -> tuple[Period, float, int] | None:
        boom("step")
        return None

    def factor_fn() -> float:
        return boom("factor")

    def keyed_fn(key: int) -> float:
        return boom(f"keyed@{key}")

    base = Series.unfold(exact, seed=0, step=step)
    other = Series.unfold(exact, seed=0, step=step, name="Other")
    factor = Fn(factor_fn)
    keyed = KeyedFn(keyed_fn)
    combined = ops.sub(
        ops.add(base, other, merge_keys=period_union),
        ops.scale(clip_periods(base, D1), factor),
        merge_keys=period_union,
    )
    rules = [base, other, factor, keyed, combined, combined._cells, base._cells]
    names = [rule.name for rule in rules]

    assert names[4] == "sub(add(…), scale(…))"
    assert names[5] == f"{names[4]}.cells"
    assert all(names)
    assert calls == []


def test_traces_show_derived_names():
    a = Series.of(exact, [(D1, 1.0)], name="A")
    b = Series.of(exact, [(D1, 2.0)], name="B")
    total = ops.add(a, b, merge_keys=date_union)
    ctx = Context()
    assert ctx.get_at(total, D1) == 3.0
    trace = str(ctx.dependencies(total, D1))
    assert trace.splitlines()[0] == "add(A, B)@datetime.date(2026, 1, 31) = 3.0"
    assert "  A@datetime.date(2026, 1, 31) = 1.0" in trace


def test_statements_require_explicit_names():
    a = Series.of(exact, [(D1, 1.0)], name="A")
    b = Series.of(exact, [(D1, 2.0)], name="B")
    total = ops.add(a, b, merge_keys=date_union)

    with pytest.raises(ValueError, match=r"explicit name.*'add\(A, B\)'"):
        stmt.Stmt(a, total)
    with pytest.raises(ValueError, match="explicit name"):
        stmt.Stmt(stmt.Total(total, [a, b]))
    with pytest.raises(ValueError, match="explicit name"):
        stmt.Stmt(stmt.Group(a, ops.neg(b)))

    named = ops.add(a, b, merge_keys=date_union, name="Total")
    stmt.Stmt(stmt.Total(named, [a, b]))
