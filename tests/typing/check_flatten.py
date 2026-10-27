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
    of_cells,
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

outer = of_cells([(0, actuals), (1, forecast)], name="components")
flat = Series.flatten(outer, query=covered, split_keys=period_split, name="flat")
assert_type(flat, Series[Period, Maybe[float], Maybe[float]])
assert_type(flat.walk(), Chain[Period, Maybe[float]])


def from_text(q: Period, cells: Chain[Period, str]) -> Effect[Maybe[float]]:
    answer = yield from exact(q, cells)
    return Na if isna(answer) else float(answer)


text_forecast = Series.of(from_text, [(Q2, "200")], name="text forecast")


def continuation(last: Cons[Period, Maybe[float]] | None) -> Series[Period, str, Maybe[float]]:
    return text_forecast


chain = continue_series(actuals, continuation, name="components")
assert_type(chain, Chain[int, Series[Period, Any, Maybe[float]]])
mixed = Series.flatten(chain, query=covered, split_keys=period_split, name="mixed")
assert_type(mixed, Series[Period, Maybe[float], Maybe[float]])

nested = of_cells([(0, actuals), (1, mixed)], name="nested")
assert_type(
    Series.flatten(nested, query=covered, split_keys=period_split, name="nested"),
    Series[Period, Maybe[float], Maybe[float]],
)
continue_series(mixed, lambda _: flat, name="nested continuation")
assert_type(
    continue_series(actuals, lambda _: None, name="ended"),
    Chain[int, Series[Period, Any, Maybe[float]]],
)
assert_type(
    continue_series(actuals, continuation, lambda _: flat, name="two continuations"),
    Chain[int, Series[Period, Any, Maybe[float]]],
)
continue_series(actuals, continuation, lambda _: dates, name="bad second keys")  # pyrefly: ignore[bad-argument-type]


# Wrong answer-node type must not be hidden by the continuation's existential V.
def wrong_anchor(last: Cons[Period, str] | None) -> Series[Period, str, Maybe[float]]:
    return text_forecast


continue_series(actuals, wrong_anchor, name="bad anchor")  # pyrefly: ignore[bad-argument-type]

# Output W remains constrained even though components may have any raw V.
labels = Series.of(exact, [(Q2, "forecast")], name="labels")
continue_series(actuals, lambda _: labels, name="bad answers")  # pyrefly: ignore[bad-argument-type]
label_components = of_cells([(0, labels)], name="label components")
Series.flatten(label_components, query=covered, split_keys=period_split, name="bad fold")  # pyrefly: ignore[bad-argument-type]

# Components and query splitting must agree on K.
Series.flatten(outer, query=covered, split_keys=date_split, name="bad split")  # pyrefly: ignore[bad-argument-type]
dates = Series.of(exact, [(date(2025, 1, 1), 100.0)], name="dates")
continue_series(actuals, lambda _: dates, name="bad keys")  # pyrefly: ignore[bad-argument-type]

# The outer chain's keys are positions, not component domain keys.
period_outer = of_cells([(Q1, actuals)], name="bad outer")
Series.flatten(period_outer, query=covered, split_keys=period_split, name="bad outer")  # pyrefly: ignore[bad-argument-type]


def plain_sum(q: Period, cells: Chain[Period, float]) -> Effect[float]:
    result = 0.0
    node = yield from get(cells)
    while node is not None:
        result += yield from get(node.value)
        node = yield from get(node.tail)
    return result


plain = Series.of(plain_sum, [(Q1, 1.0)], name="plain answers")
plain_outer = of_cells([(0, plain)], name="plain components")
assert_type(
    Series.flatten(plain_outer, query=plain_sum, split_keys=period_split, name="plain"),
    Series[Period, float, float],
)

# concat_cells joins a chain of chains; outer keys of any type are discarded.
chains = of_cells([(Q1, actuals.walk()), (Q2, forecast.walk())], name="chains")
assert_type(concat_cells(chains, name="joined"), Chain[Period, Maybe[float]])

# flat_map_cells is concat after mapping resolved outer values to chains.
pairs = of_cells([(0, (actuals, forecast))], name="pairs")
assert_type(
    flat_map_cells(pairs, lambda pair: pair[1].walk(), name="cells"), Chain[Period, Maybe[float]]
)


def actual_cells(source: Series[Period, float, Maybe[float]]) -> Chain[Period, Maybe[float]]:
    return source.walk()


assert_type(
    flat_map_cells(period_outer, actual_cells, name="period outer"), Chain[Period, Maybe[float]]
)
labelled = of_cells([("actuals", actuals)], name="labelled")
assert_type(flat_map_cells(labelled, actual_cells, name="str outer"), Chain[Period, Maybe[float]])

# The concatenated cell type follows the inner chains.
assert_type(flat_map_cells(pairs, lambda _: labels.walk(), name="labels"), Chain[Period, Maybe[str]])

# An empty series takes its types from the class subscript, not from cells.
empty = Series[Period, float, Maybe[float]].empty(accrue(YF.cmonthly), name="empty")
assert_type(empty, Series[Period, float, Maybe[float]])
assert_type(
    concat_cells(
        of_cells([(0, empty.walk()), (1, actuals.walk())], name="chains"),
        name="with empty",
    ),
    Chain[Period, Maybe[float]],
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
