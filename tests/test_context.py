from collections.abc import Callable
from datetime import date
from typing import Any

import pytest
from dateutil.relativedelta import relativedelta

from orcaset import (
    YF,
    Cell,
    Context,
    DepNode,
    Period,
    Series,
    abs_distance,
    accrue,
    get,
    get_at,
    multiply_some,
    ops,
)
from orcaset.rule import _UNIT

MONTH = relativedelta(months=1)
JAN = Period(date(2026, 1, 1), date(2026, 2, 1))
FEB = JAN.shift(MONTH)
MAR = FEB.shift(MONTH)
Q1 = Period(date(2026, 1, 1), date(2026, 4, 1))


def _literal_model():
    rev = Series.of("Revenue", accrue(YF.cmonthly), [(JAN, 100.0), (FEB, 110.0), (MAR, 121.0)])
    return rev, ops.scale("Costs", rev, -0.5)


def _recurrence_model():
    @Series.define("Revenue", accrue(YF.cmonthly), seed=JAN)
    def rev(period: Period):
        if period == JAN:
            value = 100.0
        else:
            prior = yield from get_at(rev, period.shift(-MONTH))
            value = multiply_some((prior, 1.10))
        return period, value, period.from_end(MONTH)

    return rev, ops.scale("Costs", rev, -0.5)


def _labels(path: tuple[DepNode, ...]) -> tuple[tuple[str, object], ...]:
    return tuple((node.name, node.key) for node in path)


@pytest.mark.parametrize("model", [_literal_model, _recurrence_model])
def test_crossing_query_depends_on_stored_cell(model: Callable[[], tuple[Any, Any]]) -> None:
    rev, costs = model()
    ctx = Context()
    assert ctx.depends_on((costs, Q1), (rev, JAN))
    assert ctx.depends_on((costs, Q1), (rev, Q1))
    path = ctx.path_to((costs, Q1), (rev, JAN))
    assert path is not None
    assert _labels(path) == (("Costs", Q1), ("Revenue", Q1), ("Revenue", JAN))
    assert path[-1].value == 100.0
    assert all(node.deps == () for node in path)


def test_same_key_depends_on_query_cell():
    rev, costs = _literal_model()
    ctx = Context()
    assert ctx.depends_on((costs, JAN), (rev, JAN))
    path = ctx.path_to((costs, JAN), (rev, JAN))
    assert path is not None
    assert _labels(path) == (("Costs", JAN), ("Revenue", JAN))
    assert path[-1].value == 100.0


def test_direction_and_unrelated_cells():
    rev, costs = _literal_model()
    other = Series.of("Other", accrue(YF.cmonthly), [(JAN, 1.0)])
    ctx = Context()
    assert not ctx.depends_on((rev, JAN), (costs, JAN))
    assert ctx.path_to((rev, JAN), (costs, JAN)) is None
    assert not ctx.depends_on((costs, JAN), (other, JAN))


def test_stored_key_not_unfolded_is_not_a_dependency():
    rev, costs = _literal_model()
    ctx = Context()
    assert not ctx.depends_on((costs, JAN), (rev, MAR))
    cached = len(ctx._compute_cache)
    assert not ctx.depends_on((costs, JAN), (rev, MAR))
    assert len(ctx._compute_cache) == cached, "target lookup must not force computation"


def test_materializes_source_on_fresh_context():
    rev, costs = _literal_model()
    ctx = Context()
    assert ctx._deps == {}
    assert ctx.depends_on((costs, JAN), (rev, JAN))


def test_unkeyed_rules_as_source_and_target():
    rev, costs = _literal_model()

    @Cell.define("total")
    def total():
        return (yield from get_at(costs, Q1))

    @Cell.define("leaf")
    def leaf():
        return 1.0

    @Cell.define("via leaf")
    def via_leaf():
        return ((yield from get(leaf)), (yield from get(total)))

    ctx = Context()
    assert ctx.depends_on(total, (rev, JAN))
    assert ctx.depends_on(via_leaf, leaf)
    assert not ctx.depends_on(leaf, via_leaf)
    path = ctx.path_to(via_leaf, (rev, JAN))
    assert path is not None
    assert _labels(path) == (
        ("via leaf", _UNIT),
        ("total", _UNIT),
        ("Costs", Q1),
        ("Revenue", Q1),
        ("Revenue", JAN),
    )


def test_reflexive_only_through_a_cycle():
    @Cell.define("a")
    def a():
        b_ = yield from get(b, seed=0.0, distance=abs_distance)
        return 0.5 * b_ + 1.0

    @Cell.define("b")
    def b():
        return 0.5 * (yield from get(a))

    @Cell.define("leaf")
    def leaf():
        return 1.0

    ctx = Context()
    assert ctx.depends_on(a, a)
    path = ctx.path_to(a, a)
    assert path is not None
    assert _labels(path) == (("a", _UNIT), ("b", _UNIT), ("a", _UNIT))
    assert not ctx.depends_on(leaf, leaf)
    assert ctx.path_to(leaf, leaf) is None


def test_structural_flag_keeps_chain_machinery():
    rev, costs = _literal_model()
    ctx = Context()
    folded = ctx.path_to((costs, Q1), (rev, FEB))
    full = ctx.path_to((costs, Q1), (rev, FEB), structural=True)
    assert folded is not None and full is not None
    assert not any(".cells" in n.name or ".tail@" in n.name for n in folded)
    assert len(full) >= len(folded)
    assert full[0] == folded[0] and full[-1] == folded[-1]
    assert full[-1].name == "Revenue" and full[-1].key == FEB
