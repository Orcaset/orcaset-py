"""Positive inference and expected rejections for series-valued components."""

from datetime import date
from typing import Any, assert_type

from orcaset import (
    YF,
    Chain,
    Cons,
    Effect,
    Period,
    Series,
    clip_dates,
    clip_periods,
    concat_cells,
    continue_series,
    date_split,
    flat_map_cells,
    get,
    period_split,
)
from orcaset.maybe import Maybe, Na, isna
from orcaset.query import accrue, covered, exact

Q1 = Period(date(2025, 1, 1), date(2025, 4, 1))
Q2 = Period(date(2025, 4, 1), date(2025, 7, 1))
actuals = Series.of(covered, [(Q1, 100.0)], name="actuals")
forecast = Series.of(accrue(YF.cmonthly), [(Q2, 200.0)], name="forecast")
assert_type(actuals, Series[Period, float, Maybe[float]])
assert_type(forecast, Series[Period, float, Maybe[float]])

maybe_forecast: Series[Period, Maybe[float], Maybe[float]] = Series.of(
    accrue(YF.cmonthly), [(Q2, Na)], name="maybe forecast"
)

outer = Series.of(exact, [(0, actuals), (1, forecast)], name="components")
flat = Series.flatten(outer.cells, query=covered, split_keys=period_split, name="flat")
assert_type(flat, Series[Period, Maybe[float], Maybe[float]])
assert_type(flat.cells, Chain[Period, Maybe[float]])


def from_text(q: Period, cells: Chain[Period, str]) -> Effect[Maybe[float]]:
    answer = yield from exact(q, cells)
    return Na if isna(answer) else float(answer)


text_forecast = Series.of(from_text, [(Q2, "200")], name="text forecast")


def continuation(last: Cons[Period, float] | None) -> Series[Period, str, Maybe[float]]:
    return text_forecast


chain = continue_series(actuals, continuation, name="components")
assert_type(chain, Chain[int, Series[Period, Any, Maybe[float]]])
mixed = Series.flatten(chain, query=covered, split_keys=period_split, name="mixed")
assert_type(mixed, Series[Period, Maybe[float], Maybe[float]])

nested = Series.of(exact, [(0, actuals), (1, mixed)], name="nested")
assert_type(
    Series.flatten(nested.cells, query=covered, split_keys=period_split, name="nested"),
    Series[Period, Maybe[float], Maybe[float]],
)
continue_series(mixed, lambda _: flat, name="nested continuation")


# Wrong raw-node type must not be hidden by the continuation's existential V.
def wrong_anchor(last: Cons[Period, str] | None) -> Series[Period, str, Maybe[float]]:
    return text_forecast


continue_series(actuals, wrong_anchor, name="bad anchor")  # pyrefly: ignore[bad-argument-type]

# Output W remains constrained even though components may have any raw V.
labels = Series.of(exact, [(Q2, "forecast")], name="labels")
continue_series(actuals, lambda _: labels, name="bad answers")  # pyrefly: ignore[bad-argument-type]
label_components = Series.of(exact, [(0, labels)], name="label components")
Series.flatten(label_components.cells, query=covered, split_keys=period_split, name="bad fold")  # pyrefly: ignore[bad-argument-type]

# Components and query splitting must agree on K.
Series.flatten(outer.cells, query=covered, split_keys=date_split, name="bad split")  # pyrefly: ignore[bad-argument-type]
dates = Series.of(exact, [(date(2025, 1, 1), 100.0)], name="dates")
continue_series(actuals, lambda _: dates, name="bad keys")  # pyrefly: ignore[bad-argument-type]

# The outer chain's keys are positions, not component domain keys.
period_outer = Series.of(exact, [(Q1, actuals)], name="bad outer")
Series.flatten(period_outer.cells, query=covered, split_keys=period_split, name="bad outer")  # pyrefly: ignore[bad-argument-type]


def plain_sum(q: Period, cells: Chain[Period, float]) -> Effect[float]:
    result = 0.0
    node = yield from get(cells)
    while node is not None:
        result += yield from get(node.value)
        node = yield from get(node.tail)
    return result


plain = Series.of(plain_sum, [(Q1, 1.0)], name="plain answers")
plain_outer = Series.of(exact, [(0, plain)], name="plain components")
assert_type(
    Series.flatten(plain_outer.cells, query=plain_sum, split_keys=period_split, name="plain"),
    Series[Period, float, float],
)

# concat_cells joins a chain of chains; outer keys of any type are discarded.
chains = Series.of(exact, [(Q1, actuals.cells), (Q2, forecast.cells)], name="chains")
assert_type(concat_cells(chains.cells, name="joined"), Chain[Period, float])

# flat_map_cells is concat after mapping resolved outer values to chains.
pairs = Series.of(exact, [(0, (actuals, forecast))], name="pairs")
assert_type(
    flat_map_cells(pairs.cells, lambda pair: pair[1].cells, name="cells"), Chain[Period, float]
)


def actual_cells(source: Series[Period, float, Maybe[float]]) -> Chain[Period, float]:
    return source.cells


assert_type(
    flat_map_cells(period_outer.cells, actual_cells, name="period outer"), Chain[Period, float]
)
labelled = Series.of(exact, [("actuals", actuals)], name="labelled")
assert_type(flat_map_cells(labelled.cells, actual_cells, name="str outer"), Chain[Period, float])

# The concatenated cell type follows the inner chains.
assert_type(flat_map_cells(pairs.cells, lambda _: labels.cells, name="labels"), Chain[Period, str])

# An empty series takes its cell type from the class subscript, not from cells.
empty = Series[Period, float, Maybe[float]].empty(accrue(YF.cmonthly), name="empty")
assert_type(empty, Series[Period, float, Maybe[float]])
assert_type(
    concat_cells(
        Series.of(exact, [(0, empty.cells), (1, actuals.cells)], name="chains").cells,
        name="with empty",
    ),
    Chain[Period, float],
)

# Clipping keeps the key type; trimmed period cells hold the source's answers.
assert_type(
    clip_periods(actuals, Q1.start, Q1.end, name="clipped"),
    Series[Period, Maybe[float], Maybe[float]],
)
dated = Series.of(exact, [(date(2025, 3, 31), 1.0)], name="dated")
assert_type(
    clip_dates(dated, end=date(2025, 6, 30), name="clipped"), Series[date, float, Maybe[float]]
)
clip_periods(dated, date(2025, 1, 1), name="bad keys")  # pyrefly: ignore[bad-argument-type]
clip_dates(actuals, date(2025, 1, 1), name="bad keys")  # pyrefly: ignore[bad-argument-type]
