# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from collections.abc import Callable, Generator, Hashable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, Self

from orcaset.period import Period
from orcaset.rule import Cell, KeyedRule, Rule, Step, get, get_at


class Key(Hashable, Protocol):
    """Series key: hashable (cell identity) and comparable (lazy scans).

    ``a < b`` means "a is entirely before b". The order need not be total:
    keys that overlap (e.g. overlapping ``Period``s) may be mutually
    incomparable. Scans only require that domain streams are strictly
    ascending, so anything entirely past a probe stays past it.
    """

    def __lt__(self, other: Self, /) -> bool: ...


class Thunk[V]:
    """Nominal wrapper for a deferred cell computation.

    In an unfold result, anything that is not a ``Thunk`` is a plain value,
    including callables and all other objects. Wrap deferred computation in
    ``Thunk`` explicitly. This makes the value slot unambiguous.
    """

    __slots__ = ("fn",)

    def __init__(self, fn: Callable[[], Step[V] | V]) -> None:
        self.fn = fn


@dataclass(frozen=True, slots=True)
class Cons[K: Key, V]:
    """One materialized node of a series' cell chain.

    ``tail`` resolves to the next node or ``None`` (exhaustion). Tails are
    ordinary rules: memoized per context and free to demand other rules,
    enabling value-dependent domains.
    """

    key: K
    cell: Rule[V]
    tail: Rule[Cons[K, V] | None]


type Cells[K: Key, V] = Rule[Cons[K, V] | None]
type UnfoldFn[S, K: Key, V] = Callable[
    [S],
    Step[tuple[K, V | Thunk[V], S] | None] | tuple[K, V | Thunk[V], S] | None,
]
"""Produce a cell and next state from an unfold state, or end the chain."""

type QueryFn[K: Key, V, W] = Callable[[K, Cells[K, V]], Step[W] | W]
"""Fold a query over a cell chain, with optional early termination."""

type KeyMerge[K: Key] = Callable[[K, K], tuple[K, K | None, K | None]]
"""Merge two pending heads: the first tile of their union, then what remains
of each operand after it (``None`` when consumed). ``period_union`` and
``date_union`` are the canonical instances."""


class Series[K: Key, V, W](KeyedRule[K, W]):
    """A queryable series backed by an effectful cons-list built by unfold.

    ``K`` is both the cell key type and the query type. ``V`` is the cell
    value type and ``W`` the query answer type.
    """

    def __init__(self, name: str, cells: Cells[K, V], query: QueryFn[K, V, W]) -> None:
        super().__init__(name)
        self._cells = cells
        self._query = query

    @property
    def cells(self) -> Cells[K, V]:
        """The rule resolving the first node of this series."""
        return self._cells

    def compute(self, q: K, /) -> Step[W]:
        return (yield from _as_step(self._query(q, self._cells)))

    @classmethod
    def unfold[S](
        cls,
        name: str,
        query: QueryFn[K, V, W],
        *,
        seed: S,
        step: UnfoldFn[S, K, V],
    ) -> Series[K, V, W]:
        """Build a series by repeatedly applying ``step`` to an evolving state."""
        return cls(name, unfold_cells(name, seed=seed, step=step), query)

    @classmethod
    def extend(
        cls,
        name: str,
        query: QueryFn[K, V, W],
        *,
        base: Cells[K, V],
        cont: Callable[[K | None], Cells[K, V]],
    ) -> Series[K, V, W]:
        """Build a series that continues ``base`` lazily at its frontier."""
        return cls(name, extend_cells(name, base, cont), query)

    @classmethod
    def append(
        cls,
        name: str,
        query: QueryFn[K, V, W],
        *,
        first: Cells[K, V],
        then: Cells[K, V],
    ) -> Series[K, V, W]:
        """Build a series by appending ``then`` after ``first``."""
        return cls(name, append_cells(name, first, then), query)

    @classmethod
    def of(
        cls,
        name: str,
        query: QueryFn[K, V, W],
        pairs: Iterable[tuple[K, V | Thunk[V]]],
    ) -> Series[K, V, W]:
        """Build a series from eagerly materialized literal pairs."""
        materialized = tuple(pairs)

        def step(index: int) -> tuple[K, V | Thunk[V], int] | None:
            if index == len(materialized):
                return None
            key, value = materialized[index]
            return key, value, index + 1

        return cls.unfold(name, query, seed=0, step=step)

    @classmethod
    def define[S](
        cls,
        name: str,
        query: QueryFn[K, V, W],
        *,
        seed: S,
    ) -> Callable[[UnfoldFn[S, K, V]], Series[K, V, W]]:
        """Decorator form of ``unfold`` for self-referential series bodies."""

        def decorator(step: UnfoldFn[S, K, V]) -> Series[K, V, W]:
            return cls.unfold(name, query, seed=seed, step=step)

        return decorator


class _UnfoldRule[S, K: Key, V](Rule[Cons[K, V] | None]):
    """Rule that materializes one unfold node and its deferred tail."""

    def __init__(
        self,
        series_name: str,
        prev_key: K | None,
        state: S,
        step: UnfoldFn[S, K, V],
    ) -> None:
        name = f"{series_name}.cells" if prev_key is None else f"{series_name}.tail@{prev_key}"
        super().__init__(name)
        self._series_name = series_name
        self._prev_key = prev_key
        self._state = state
        self._step = step

    def compute(self) -> Step[Cons[K, V] | None]:
        result = yield from _as_step(self._step(self._state))
        if result is None:
            return None
        key, value, next_state = result
        if self._prev_key is not None and not self._prev_key < key:
            raise ValueError(
                f"keys must be strictly ascending: got {self._prev_key!r} then {key!r}"
            )
        return Cons(
            key,
            Cell(f"{self._series_name}@{key}", _cell_fn(value)),
            _UnfoldRule(self._series_name, key, next_state, self._step),
        )


def unfold_cells[S, K: Key, V](
    name: str,
    *,
    seed: S,
    step: UnfoldFn[S, K, V],
) -> Cells[K, V]:
    """Build a standalone cell chain, e.g. for an ``extend_cells`` continuation."""
    return _UnfoldRule(name, None, seed, step)


def map_cells[K: Key, A, B](
    name: str,
    source: Cells[K, A],
    fn: Callable[[K, Rule[A]], B | Thunk[B]],
) -> Cells[K, B]:
    """Map cells one-for-one without forcing their values."""

    def step(cells: Cells[K, A]) -> Step[tuple[K, B | Thunk[B], Cells[K, A]] | None]:
        node = yield from get(cells)
        if node is None:
            return None
        return node.key, fn(node.key, node.cell), node.tail

    return unfold_cells(name, seed=source, step=step)


def scan_cells[K: Key, A, S, B](
    name: str,
    source: Cells[K, A],
    *,
    seed: S,
    fn: Callable[[S, K, Rule[A]], tuple[B | Thunk[B], S]],
) -> Cells[K, B]:
    """Map cells one-for-one while carrying structural accumulator state."""

    def step(
        state: tuple[Cells[K, A], S],
    ) -> Step[tuple[K, B | Thunk[B], tuple[Cells[K, A], S]] | None]:
        cells, acc = state
        node = yield from get(cells)
        if node is None:
            return None
        value, next_acc = fn(acc, node.key, node.cell)
        return node.key, value, (node.tail, next_acc)

    return unfold_cells(name, seed=(source, seed), step=step)


class _SpliceRule[K: Key, V](Rule[Cons[K, V] | None]):
    """Splice a continuation onto a source chain when its frontier is reached.

    Clipping assumes the usual transitivity of the key order: along an
    ascending chain, nodes entirely after the last base key keep surviving.
    """

    def __init__(
        self,
        series_name: str,
        prev_key: K | None,
        source: Cells[K, V],
        cont: Callable[[K | None], Cells[K, V]],
    ) -> None:
        name = f"{series_name}.cells" if prev_key is None else f"{series_name}.tail@{prev_key}"
        super().__init__(name)
        self._series_name = series_name
        self._prev_key = prev_key
        self._source = source
        self._cont = cont

    def compute(self) -> Step[Cons[K, V] | None]:
        node = yield from get(self._source)
        if node is not None:
            return Cons(
                node.key,
                node.cell,
                _SpliceRule(self._series_name, node.key, node.tail, self._cont),
            )

        cont_cells = self._cont(self._prev_key)
        node = yield from get(cont_cells)
        while node is not None and self._prev_key is not None and not self._prev_key < node.key:
            node = yield from get(node.tail)
        return node


def extend_cells[K: Key, V](
    name: str,
    base: Cells[K, V],
    cont: Callable[[K | None], Cells[K, V]],
) -> Cells[K, V]:
    """Continue ``base`` lazily with a chain built from its last key.

    ``cont`` receives the last base key, or ``None`` for an empty base, and is
    invoked only when a walk reaches the base frontier. Leading continuation
    nodes not entirely after the last base key are clipped.
    """
    return _SpliceRule(name, None, base, cont)


def append_cells[K: Key, V](
    name: str,
    first: Cells[K, V],
    then: Cells[K, V],
) -> Cells[K, V]:
    """Append ``then`` after ``first``; overlap with ``first`` is clipped."""
    return extend_cells(name, first, lambda _last: then)


def extend_period_series[V, W](
    name: str,
    base: Series[Period, V, W],
    cont: Callable[[Period | None], Series[Period, V, W]],
    combine: Callable[[W, W], W],
) -> Series[Period, V, W]:
    """Continue a finite period series while preserving both query policies.

    Queries entirely on one side of the base frontier use that side's query
    function. A query crossing the frontier is split there and its two answers
    are passed to ``combine``. The continuation is created lazily and cached.
    """
    continuations: dict[Period | None, Series[Period, V, W]] = {}

    def continuation(last: Period | None) -> Series[Period, V, W]:
        result = continuations.get(last)
        if result is None:
            result = cont(last)
            continuations[last] = result
        return result

    def query(q: Period, _cells: Cells[Period, V]) -> Step[W]:
        node = yield from get(base.cells)
        last: Period | None = None
        while node is not None:
            last = node.key
            node = yield from get(node.tail)

        if last is None:
            return (yield from get_at(continuation(None), q))
        if q.end <= last.end:
            return (yield from get_at(base, q))

        following = continuation(last)
        if q.start >= last.end:
            return (yield from get_at(following, q))

        left = yield from get_at(base, Period(q.start, last.end))
        right = yield from get_at(following, Period(last.end, q.end))
        return combine(left, right)

    cells = extend_cells(name, base.cells, lambda last: continuation(last).cells)
    return Series(name, cells, query)


type _Frontier[K: Key] = tuple[K | None, Cells[K, Any] | None]
"""One merge operand: pending head not yet emitted past, and the rest of its
chain. ``(None, tail)`` needs a refill; ``(None, None)`` is exhausted."""


def merge_cells[K: Key, V](
    name: str,
    chains: Sequence[Cells[K, Any]],
    merge: KeyMerge[K],
    cell: Callable[[K], V | Thunk[V]],
) -> Cells[K, V]:
    """Merge ascending chains into one chain whose keys re-tile their union.

    The merged domain is produced lazily with one pending head of lookahead
    per operand; source cells are never forced, only tail rules. Each emitted
    key is the first tile of the union of the pending heads under ``merge``
    (folded pairwise), and ``cell`` supplies the value at that key — typically
    a ``Thunk`` that queries the source series by key, since split tiles need
    not exist as nodes in any source.

    ``merge`` must satisfy the refold law: with ``piece`` the folded first
    tile, ``merge(piece, head)`` returns ``(piece, None, rest_of_head)`` for
    every pending head. ``period_union`` and ``date_union`` comply; violations
    raise ``ValueError``.
    """

    def step(
        frontiers: tuple[_Frontier[K], ...],
    ) -> Step[tuple[K, V | Thunk[V], tuple[_Frontier[K], ...]] | None]:
        refilled: list[_Frontier[K]] = []
        for pending, tail in frontiers:
            if pending is None and tail is not None:
                node = yield from get(tail)
                pending, tail = (node.key, node.tail) if node is not None else (None, None)
            refilled.append((pending, tail))

        heads = [key for key, _ in refilled if key is not None]
        if not heads:
            return None

        piece = heads[0]
        for head in heads[1:]:
            piece, _, _ = merge(piece, head)

        advanced: list[_Frontier[K]] = []
        for pending, tail in refilled:
            if pending is None:
                advanced.append((pending, tail))
                continue
            emitted, rest_piece, rest = merge(piece, pending)
            if emitted != piece or rest_piece is not None:
                raise ValueError(
                    f"key merge violates the refold law: merge({piece!r}, {pending!r}) "
                    f"returned {(emitted, rest_piece, rest)!r}; "
                    f"expected ({piece!r}, None, <remainder>)"
                )
            advanced.append((rest, tail))

        return piece, cell(piece), tuple(advanced)

    seed: tuple[_Frontier[K], ...] = tuple((None, chain) for chain in chains)
    return unfold_cells(name, seed=seed, step=step)


def _cell_fn[V](value: V | Thunk[V]) -> Callable[[], Step[V] | V]:
    if isinstance(value, Thunk):
        return value.fn
    if isinstance(value, Generator):
        raise TypeError(
            "live generator as a cell value; wrap the computation in Thunk(lambda: ...)"
        )
    return lambda value=value: value


def _as_step[V](value: Step[V] | V) -> Step[V]:
    """Normalize plain and generator return values to a ``Step``."""
    if isinstance(value, Generator):
        return value

    def completed() -> Step[V]:
        if False:
            yield
        return value

    return completed()


def first_key[K: Key, V](cells: Cells[K, V]) -> Step[K | None]:
    """Return the first key, or ``None`` when the chain is empty."""
    node = yield from get(cells)
    return None if node is None else node.key


def last_key[K: Key, V](cells: Cells[K, V]) -> Step[K | None]:
    """Return the last key of a finite chain, or ``None`` when empty."""
    node = yield from get(cells)
    result: K | None = None
    while node is not None:
        result = node.key
        node = yield from get(node.tail)
    return result


def collect_keys[K: Key, V](
    cells: Cells[K, V],
    *,
    through: K | None = None,
    limit: int | None = None,
) -> Step[list[K]]:
    """Collect keys up to an inclusive bound and/or count limit.

    At least one bound is required to terminate on an infinite chain.
    """
    if limit is not None and limit < 0:
        raise ValueError("limit must be non-negative")
    keys: list[K] = []
    if limit == 0:
        return keys
    node = yield from get(cells)
    while node is not None:
        if through is not None and through < node.key:
            break
        keys.append(node.key)
        if limit is not None and len(keys) == limit:
            break
        node = yield from get(node.tail)
    return keys


def keys_until[K: Key, V](cells: Cells[K, V], stop: K) -> Step[list[K]]:
    """Collect keys through ``stop`` without forcing cells or a past frontier."""
    keys: list[K] = []
    node = yield from get(cells)
    while node is not None:
        if stop < node.key:
            break
        keys.append(node.key)
        node = yield from get(node.tail)
    return keys
