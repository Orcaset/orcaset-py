# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from collections.abc import Callable, Iterable, Iterator, Sequence
from heapq import merge
from itertools import count, islice

import pytest

from orcaset import (
    Context,
    GridSeries,
    Keys,
    MapNSeries,
    MapSeries,
    Maybe,
    Na,
    Rule,
    Series,
    ValueFn,
    isna,
)

# ---------- a minimal test kind: exact-key lookup, misses answer Na ----------


def _point_select(keys: Keys[int], q: int) -> Sequence[int]:
    for k in keys:
        if k == q:
            return [k]
        if q < k:
            return []
    return []


def _point_reduce(q: int, items: Sequence[tuple[int, Maybe[float]]]) -> Maybe[float]:
    return items[0][1] if items else Na


def PointSeries(
    name: str,
    keys: Rule[None, Keys[int]] | Callable[[], Iterable[int]],
    value_at: ValueFn[int, float],
) -> GridSeries[int, int, float, Maybe[float]]:
    """Construction helper pairing the point select/reduce semantics."""
    return GridSeries(name, keys, value_at, select=_point_select, reduce=_point_reduce)


def _merge_int_keys(domains: tuple[Keys[int], ...]) -> Iterator[int]:
    previous: int | None = None
    for key in merge(*domains):
        if key != previous:
            yield key
            previous = key


# ---------- grid template ----------


def test_value_at_is_instance_state_on_a_shared_kind():
    revenue = PointSeries("revenue", lambda: range(3), lambda s, k: 100.0 + k)
    costs = PointSeries("costs", lambda: range(3), lambda s, k: 7.0 * k)
    ctx = Context()
    assert ctx.demand(revenue, 1) == 101.0
    assert ctx.demand(costs, 1) == 7.0


def test_off_domain_query_answers_na():
    s = PointSeries("s", lambda: range(3), lambda s, k: float(k))
    ctx = Context()
    assert isna(ctx.demand(s, 99))
    assert ctx.demand(s, 2) == 2.0


def test_value_at_may_be_a_plain_value_or_a_step():
    plain = PointSeries("plain", lambda: range(2), lambda s, k: 1.0)

    def stepped(s, k):
        v = yield from s.cell(k - 1)
        return 1.0 if isna(v) else v + 1.0

    step = PointSeries("step", lambda: range(2), stepped)
    ctx = Context()
    assert ctx.demand(plain, 0) == 1.0
    assert ctx.demand(step, 1) == 2.0


def test_recurrence_via_cell_and_cells_memoized_per_context():
    calls = []

    def growth(s, k):
        calls.append(k)
        prior = yield from s.cell(k - 1)
        return 100.0 if isna(prior) else prior * 2

    s = PointSeries("s", lambda: range(5), growth)
    ctx = Context()
    assert ctx.demand(s, 4) == 1600.0
    assert calls == [4, 3, 2, 1, 0]
    calls.clear()
    assert ctx.demand(s, 3) == 800.0  # cells cached; no recompute
    assert calls == []


def test_shared_keys_rule_buffers_key_source_once_per_context():
    pulls = count()

    def keygen():
        for k in range(3):
            next(pulls)
            yield k

    revenue = PointSeries("revenue", keygen, lambda s, k: 1.0)
    costs = PointSeries("costs", revenue.keys, lambda s, k: 2.0)
    ctx = Context()
    ctx.demand(revenue, 2)
    ctx.demand(costs, 2)
    assert next(pulls) == 3  # one shared Replayable buffer; source consumed once


def test_misordered_keys_raise_when_scanned():
    s = PointSeries("s", lambda: [2, 1], lambda s, k: 1.0)
    with pytest.raises(ValueError, match="ascending"):
        Context().demand(s, 3)  # scans past the misordered key (validation is lazy)


# ---------- map ----------


def test_map_transforms_the_source_answer_per_query():
    src = PointSeries("src", lambda: range(3), lambda s, k: float(k))
    doubled = src.map("doubled", lambda w: Na if isna(w) else w * 2)
    ctx = Context()
    assert ctx.demand(doubled, 2) == 4.0
    assert isna(ctx.demand(doubled, 99))


def test_map_fn_sees_the_raw_maybe_answer():
    src = PointSeries("src", lambda: range(2), lambda s, k: float(k))
    filled = src.map("filled", lambda w: 0.0 if isna(w) else w)
    ctx = Context()
    assert ctx.demand(filled, 99) == 0.0  # fn owns the miss policy


def test_map_aliases_source_keys():
    src = PointSeries("src", lambda: range(3), lambda s, k: float(k))
    mapped = src.map("mapped", lambda w: w)
    assert mapped.keys is src.keys
    downstream = PointSeries("downstream", mapped.keys, lambda s, k: 1.0)
    assert downstream.keys is src.keys


def test_map_is_a_series_and_composes():
    src = PointSeries("src", lambda: range(3), lambda s, k: float(k))
    mapped: Series[int, int, Maybe[float]] = src.map("mapped", lambda w: Na if isna(w) else w + 1)
    again = mapped.map("again", lambda w: Na if isna(w) else w * 10)
    assert isinstance(mapped, MapSeries)
    assert Context().demand(again, 2) == 30.0


def test_map_delegates_resolution_to_the_source_semantics():
    src = PointSeries("src", lambda: range(3), lambda s, k: float(k))
    mapped = src.map("mapped", lambda w: Na if isna(w) else w * 2)
    ctx = Context()
    tree = ctx.dependencies(mapped, 1)
    assert tree.name == "mapped"
    assert [d.name for d in tree.deps] == ["src"]  # answer built from src@q


def test_map_answers_memoized_per_query():
    hits = count()

    def fn(w):
        next(hits)
        return w

    src = PointSeries("src", lambda: range(3), lambda s, k: float(k))
    mapped = src.map("mapped", fn)
    ctx = Context()
    ctx.demand(mapped, 1)
    ctx.demand(mapped, 1)
    assert next(hits) == 1


# ---------- map n ----------


def test_map_n_combines_source_answers_at_the_same_query():
    left = PointSeries("left", lambda: range(3), lambda s, k: float(k))
    right = PointSeries("right", lambda: range(1, 4), lambda s, k: float(k * 10))
    combined = MapNSeries(
        "combined",
        (left, right),
        lambda values: values,
        merge_keys=_merge_int_keys,
    )
    ctx = Context()

    assert ctx.demand(combined, 2) == (2.0, 20.0)
    assert ctx.demand(combined, 0) == (0.0, Na)


def test_map_n_merged_keys_are_lazy_replayable_and_unique():
    evens = PointSeries("evens", lambda: count(0, 2), lambda s, k: float(k))
    odds = PointSeries("odds", lambda: count(1, 2), lambda s, k: float(k))
    combined = MapNSeries(
        "combined",
        (evens, odds),
        lambda values: values,
        merge_keys=_merge_int_keys,
    )
    ctx = Context()

    keys = ctx.demand(combined.keys, None)
    assert list(islice(keys, 6)) == [0, 1, 2, 3, 4, 5]
    assert list(islice(keys, 6)) == [0, 1, 2, 3, 4, 5]


def test_map_n_keys_trace_dependencies_on_every_source_domain():
    left = PointSeries("left", lambda: range(2), lambda s, k: float(k))
    right = PointSeries("right", lambda: range(2), lambda s, k: float(k))
    combined = MapNSeries(
        "combined",
        (left, right),
        lambda values: values,
        merge_keys=_merge_int_keys,
    )

    tree = Context().dependencies(combined.keys, None)
    assert tree.name == "combined.keys"
    assert [dependency.name for dependency in tree.deps] == ["left.keys", "right.keys"]


def test_map_n_rejects_an_empty_source_tuple_at_runtime():
    with pytest.raises(ValueError, match="at least one source"):
        MapNSeries("empty", (), lambda values: values, merge_keys=_merge_int_keys)  # type: ignore
