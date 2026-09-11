"""Type inference for series operations."""

from collections.abc import Sequence
from datetime import date
from typing import assert_type

from orcaset import Cell, Effect, Rule, Series, date_union, get, ops
from orcaset.maybe import Maybe
from orcaset.query import exact

D = date(2026, 1, 31)
left_values: list[tuple[date, Maybe[int]]] = [(D, 1)]
left: Series[date, Maybe[int], Maybe[int]] = Series.of("left", exact, left_values)
right: Series[date, str, Maybe[str]] = Series.of("right", exact, [(D, "value")])


def format_values(left_value: Maybe[int], right_value: Maybe[str]) -> str:
    return f"{left_value}: {right_value}"


combined = ops.map2(
    "combined",
    left,
    right,
    fn=format_values,
    merge_keys=date_union,
)
assert_type(combined, Series[date, str, str])


def join_values(values: Sequence[Maybe[int]]) -> str:
    return ", ".join(map(str, values))


combined_many = ops.combine(
    "combined many",
    (left,),
    fn=join_values,
    merge_keys=date_union,
)
assert_type(combined_many, Series[date, str, str])

prefix = Cell("prefix", lambda: "value")


def format_values_effect(left_value: Maybe[int], right_value: Maybe[str]) -> Effect[str]:
    label = yield from get(prefix)
    return f"{label}: {left_value}: {right_value}"


combined_effect = ops.map2(
    "combined effect",
    left,
    right,
    fn=format_values_effect,
    merge_keys=date_union,
)
assert_type(combined_effect, Series[date, str, str])


def join_values_effect(values: Sequence[Maybe[int]]) -> Effect[str]:
    label = yield from get(prefix)
    return f"{label}: {', '.join(map(str, values))}"


combined_many_effect = ops.combine(
    "combined many effect",
    (left,),
    fn=join_values_effect,
    merge_keys=date_union,
)
assert_type(combined_many_effect, Series[date, str, str])


def format_effect(value: Maybe[int]) -> Effect[str]:
    label = yield from get(prefix)
    return f"{label}: {value}"


mapped = ops.map_values("mapped", left, fn=format_effect)
assert_type(mapped, Series[date, str, str])
plain_mapped = ops.map_values("plain mapped", left, fn=str)
assert_type(plain_mapped, Series[date, str, str])

factor = Cell("factor", lambda: 2.0)
rule_factor: Rule[float] = factor
numeric: Series[date, float, Maybe[float]] = Series.of("numeric", exact, [(D, 1.0)])
assert_type(ops.scale("literal", numeric, 2.0), Series[date, Maybe[float], Maybe[float]])
assert_type(ops.scale("cell", numeric, factor), Series[date, Maybe[float], Maybe[float]])
assert_type(ops.scale("rule", numeric, rule_factor), Series[date, Maybe[float], Maybe[float]])
ops.scale("bad factor", numeric, prefix)  # pyrefly: ignore[bad-argument-type]
