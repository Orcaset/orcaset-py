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
actuals = Series.of("actuals", covered, [(Q1, 100.0)])
forecast = Series.of("forecast", accrue(YF.cmonthly), [(Q2, 200.0)])
assert_type(actuals, Series[Period, float, Maybe[float]])
assert_type(forecast, Series[Period, float, Maybe[float]])

maybe_forecast: Series[Period, Maybe[float], Maybe[float]] = Series.of(
    "maybe forecast", accrue(YF.cmonthly), [(Q2, Na)]
)

outer = Series.of("components", exact, [(0, actuals), (1, forecast)])
flat = Series.flatten("flat", outer.cells, query=covered, split_keys=period_split)
assert_type(flat, Series[Period, Maybe[float], Maybe[float]])
assert_type(flat.cells, Chain[Period, Maybe[float]])


def from_text(q: Period, cells: Chain[Period, str]) -> Effect[Maybe[float]]:
    answer = yield from exact(q, cells)
    return Na if isna(answer) else float(answer)


text_forecast = Series.of("text forecast", from_text, [(Q2, "200")])


def continuation(last: Cons[Period, float] | None) -> Series[Period, str, Maybe[float]]:
    return text_forecast


chain = continue_series("components", actuals, continuation)
assert_type(chain, Chain[int, Series[Period, Any, Maybe[float]]])
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


def plain_sum(q: Period, cells: Chain[Period, float]) -> Effect[float]:
    result = 0.0
    node = yield from get(cells)
    while node is not None:
        result += yield from get(node.value)
        node = yield from get(node.tail)
    return result


plain = Series.of("plain answers", plain_sum, [(Q1, 1.0)])
plain_outer = Series.of("plain components", exact, [(0, plain)])
assert_type(
    Series.flatten("plain", plain_outer.cells, query=plain_sum, split_keys=period_split),
    Series[Period, float, float],
)

# concat_cells joins a chain of chains; outer keys of any type are discarded.
chains = Series.of("chains", exact, [(Q1, actuals.cells), (Q2, forecast.cells)])
assert_type(concat_cells("joined", chains.cells), Chain[Period, float])

# flat_map_cells is concat after mapping resolved outer values to chains.
pairs = Series.of("pairs", exact, [(0, (actuals, forecast))])
assert_type(flat_map_cells("cells", pairs.cells, lambda pair: pair[1].cells), Chain[Period, float])


def actual_cells(source: Series[Period, float, Maybe[float]]) -> Chain[Period, float]:
    return source.cells


assert_type(flat_map_cells("period outer", period_outer.cells, actual_cells), Chain[Period, float])
labelled = Series.of("labelled", exact, [("actuals", actuals)])
assert_type(flat_map_cells("str outer", labelled.cells, actual_cells), Chain[Period, float])

# The concatenated cell type follows the inner chains.
assert_type(flat_map_cells("labels", pairs.cells, lambda _: labels.cells), Chain[Period, str])

# An empty series takes its cell type from the class subscript, not from cells.
empty = Series[Period, float, Maybe[float]].empty("empty", accrue(YF.cmonthly))
assert_type(empty, Series[Period, float, Maybe[float]])
assert_type(
    concat_cells(
        "with empty", Series.of("chains", exact, [(0, empty.cells), (1, actuals.cells)]).cells
    ),
    Chain[Period, float],
)

# Clipping keeps the key type; trimmed period cells hold the source's answers.
assert_type(
    clip_periods("clipped", actuals, Q1.start, Q1.end), Series[Period, Maybe[float], Maybe[float]]
)
dated = Series.of("dated", exact, [(date(2025, 3, 31), 1.0)])
assert_type(clip_dates("clipped", dated, end=date(2025, 6, 30)), Series[date, float, Maybe[float]])
clip_periods("bad keys", dated, date(2025, 1, 1))  # pyrefly: ignore[bad-argument-type]
clip_dates("bad keys", actuals, date(2025, 1, 1))  # pyrefly: ignore[bad-argument-type]
