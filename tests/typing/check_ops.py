"""Type inference for series operations."""

from collections.abc import Sequence
from datetime import date
from typing import assert_type

from orcaset import Effect, Rule, Series, Val, date_union, get, ops
from orcaset.maybe import Maybe
from orcaset.query import exact

D = date(2026, 1, 31)
left_values: list[tuple[date, Maybe[int]]] = [(D, 1)]
left: Series[date, Maybe[int], Maybe[int]] = Series.of(exact, left_values, name="left")
right: Series[date, str, Maybe[str]] = Series.of(exact, [(D, "value")], name="right")


def format_values(left_value: Maybe[int], right_value: Maybe[str]) -> str:
    return f"{left_value}: {right_value}"


combined = ops.map2(
    left,
    right,
    fn=format_values,
    merge_keys=date_union,
    name="combined",
)
assert_type(combined, Series[date, str, str])


def join_values(values: Sequence[Maybe[int]]) -> str:
    return ", ".join(map(str, values))


combined_many = ops.mapn(
    (left,),
    fn=join_values,
    merge_keys=date_union,
    name="combined many",
)
assert_type(combined_many, Series[date, str, str])

prefix = Val("value", name="prefix")


def format_values_effect(left_value: Maybe[int], right_value: Maybe[str]) -> Effect[str]:
    label = yield from get(prefix)
    return f"{label}: {left_value}: {right_value}"


combined_effect = ops.map2(
    left,
    right,
    fn=format_values_effect,
    merge_keys=date_union,
    name="combined effect",
)
assert_type(combined_effect, Series[date, str, str])


def join_values_effect(values: Sequence[Maybe[int]]) -> Effect[str]:
    label = yield from get(prefix)
    return f"{label}: {', '.join(map(str, values))}"


combined_many_effect = ops.mapn(
    (left,),
    fn=join_values_effect,
    merge_keys=date_union,
    name="combined many effect",
)
assert_type(combined_many_effect, Series[date, str, str])


def format_effect(value: Maybe[int]) -> Effect[str]:
    label = yield from get(prefix)
    return f"{label}: {value}"


mapped = ops.map(left, fn=format_effect, name="mapped")
assert_type(mapped, Series[date, str, str])
plain_mapped = ops.map(left, fn=str, name="plain mapped")
assert_type(plain_mapped, Series[date, str, str])

factor = Val(2.0, name="factor")
rule_factor: Rule[float] = factor
numeric: Series[date, float, Maybe[float]] = Series.of(exact, [(D, 1.0)], name="numeric")
assert_type(ops.scale(numeric, 2.0, name="literal"), Series[date, Maybe[float], Maybe[float]])
assert_type(ops.scale(numeric, factor, name="cell"), Series[date, Maybe[float], Maybe[float]])
assert_type(ops.scale(numeric, rule_factor, name="rule"), Series[date, Maybe[float], Maybe[float]])
ops.scale(numeric, prefix, name="bad factor")  # pyrefly: ignore[bad-argument-type]
