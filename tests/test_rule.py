# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from math import isclose

import orcaset
from orcaset import (
    Cell,
    Context,
    KeyedCell,
    KeyedRule,
    PeriodSeries,
    Rule,
    Step,
    abs_distance,
    exact,
    get,
    get_at,
)


def test_rule_fn_plain_value():
    rule = Cell("src", lambda: 10.0)
    assert rule.fn() == 10.0
    assert Context().get(rule) == 10.0
    assert isinstance(rule, Rule)
    assert isinstance(rule, Cell)


def test_rule_fn_is_public_and_replaceable():
    rule = Cell("src", lambda: 1.0)
    rule.fn = lambda: 2.0
    assert Context().get(rule) == 2.0


def test_rule_define_can_demand_another_rule():
    src = Cell("src", lambda: 10.0)

    @Cell.define("reader")
    def reader() -> Step[float]:
        return (yield from get(src))

    assert reader.name == "reader"
    assert Context().get(reader) == 10.0


def test_rule_define_self_cycle():
    @Cell.define("x")
    def x() -> Step[float]:
        prior = yield from get(x, seed=1.0, distance=abs_distance)
        return 0.5 * prior + 1.0

    assert isclose(Context().get(x), 2.0)


def test_rule_subclass_passes_fn_to_super():
    class Named(Cell[float]):
        def __init__(self, name: str, value: float) -> None:
            self.value = value
            super().__init__(name, lambda: self.value)

    assert Context().get(Named("n", 3.0)) == 3.0


def test_keyed_rule_fn():
    rule = KeyedCell[int, int]("double", lambda key: key * 2)
    assert rule.fn(3) == 6
    assert Context().get_at(rule, 3) == 6
    assert isinstance(rule, KeyedRule)
    assert isinstance(rule, KeyedCell)


def test_keyed_rule_define():
    @KeyedCell.define("inc")
    def inc(key: int) -> int:
        return key + 1

    assert inc.name == "inc"
    assert Context().get_at(inc, 4) == 5


def test_keyed_rule_define_can_demand_self():
    @KeyedCell.define("k")
    def k(key: int) -> Step[int]:
        if key <= 0:
            return 0
        prev = yield from get_at(k, key - 1)
        return prev + key

    assert Context().get_at(k, 3) == 6


def test_series_is_keyed_rule_not_keyed_cell():
    series = PeriodSeries("empty", lambda: [], exact)
    assert isinstance(series, KeyedRule)
    assert not isinstance(series, KeyedCell)


def test_rule_classes_are_exported():
    expected = {
        "Cell": Cell,
        "Rule": Rule,
        "KeyedCell": KeyedCell,
        "KeyedRule": KeyedRule,
    }
    for name, cls in expected.items():
        assert name in orcaset.__all__
        assert getattr(orcaset, name) is cls
