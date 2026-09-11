"""Type inference for series operations."""

from collections.abc import Sequence
from datetime import date
from typing import assert_type

from orcaset import Series, date_union, ops
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
