"""Type inference for series operations."""

from datetime import date
from typing import assert_type

from orcaset import Maybe, Series, date_union, exact, ops

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
