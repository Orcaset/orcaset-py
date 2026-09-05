"""Positive inference and expected rejections for series-valued components."""

from datetime import date
from typing import Any, assert_type

from orcaset import (
    YF,
    Cells,
    Cons,
    Effect,
    Maybe,
    Na,
    Period,
    Series,
    accrue,
    continue_series,
    covered,
    date_split,
    exact,
    get,
    isna,
    period_split,
)

Q1 = Period(date(2025, 1, 1), date(2025, 4, 1))
Q2 = Period(date(2025, 4, 1), date(2025, 7, 1))
actuals = Series.of("actuals", covered, [(Q1, 100.0)])
forecast = Series.of("forecast", accrue(YF.cmonthly), [(Q2, 200.0)])
assert_type(actuals, Series[Period, float, Maybe[float]])

outer = Series.of("components", exact, [(0, actuals), (1, forecast)])
flat = Series.flatten("flat", outer.cells, query=covered, split_keys=period_split)
assert_type(flat, Series[Period, Maybe[float], Maybe[float]])
assert_type(flat.cells, Cells[Period, Maybe[float]])


def from_text(q: Period, cells: Cells[Period, str]) -> Effect[Maybe[float]]:
    answer = yield from exact(q, cells)
    return Na if isna(answer) else float(answer)


text_forecast = Series.of("text forecast", from_text, [(Q2, "200")])


def continuation(last: Cons[Period, float] | None) -> Series[Period, str, Maybe[float]]:
    return text_forecast


chain = continue_series("components", actuals, continuation)
assert_type(chain, Cells[int, Series[Period, Any, Maybe[float]]])
mixed = Series.flatten("mixed", chain, query=covered, split_keys=period_split)
assert_type(mixed, Series[Period, Maybe[float], Maybe[float]])

nested = Series.of("nested", exact, [(0, actuals), (1, mixed)])
assert_type(
    Series.flatten("nested", nested.cells, query=covered, split_keys=period_split),
    Series[Period, Maybe[float], Maybe[float]],
)
continue_series("nested continuation", mixed, lambda _: flat)


# Wrong raw-node type must not be hidden by the continuation's existential V.
def wrong_anchor(last: Cons[Period, str] | None) -> Series[Period, str, Maybe[float]]:
    return text_forecast


continue_series("bad anchor", actuals, wrong_anchor)  # pyrefly: ignore[bad-argument-type]

# Output W remains constrained even though components may have any raw V.
labels = Series.of("labels", exact, [(Q2, "forecast")])
continue_series("bad answers", actuals, lambda _: labels)  # pyrefly: ignore[bad-argument-type]
label_components = Series.of("label components", exact, [(0, labels)])
Series.flatten("bad fold", label_components.cells, query=covered, split_keys=period_split)  # pyrefly: ignore[bad-argument-type]

# Components and query splitting must agree on K.
Series.flatten("bad split", outer.cells, query=covered, split_keys=date_split)  # pyrefly: ignore[bad-argument-type]
dates = Series.of("dates", exact, [(date(2025, 1, 1), 100.0)])
continue_series("bad keys", actuals, lambda _: dates)  # pyrefly: ignore[bad-argument-type]

# The outer chain's keys are positions, not component domain keys.
period_outer = Series.of("bad outer", exact, [(Q1, actuals)])
Series.flatten("bad outer", period_outer.cells, query=covered, split_keys=period_split)  # pyrefly: ignore[bad-argument-type]


def plain_sum(q: Period, cells: Cells[Period, float]) -> Effect[float]:
    result = 0.0
    node = yield from get(cells)
    while node is not None:
        result += yield from get(node.cell)
        node = yield from get(node.tail)
    return result


plain = Series.of("plain answers", plain_sum, [(Q1, 1.0)])
plain_outer = Series.of("plain components", exact, [(0, plain)])
assert_type(
    Series.flatten("plain", plain_outer.cells, query=plain_sum, split_keys=period_split),
    Series[Period, float, float],
)
