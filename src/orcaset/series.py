# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from collections.abc import Callable, Generator, Hashable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol, Self, cast, overload

from orcaset.maybe import Maybe, Na
from orcaset.period import Period
from orcaset.rule import (
    AutoName,
    Effect,
    Fn,
    KeyedRule,
    Rule,
    _fn_name,
    auto_name,
    derived_name,
    get,
    get_at,
)


class Key(Hashable, Protocol):
    """Series key: hashable (cell identity) and comparable (lazy scans).

    ``a < b`` means "a is entirely before b". The order need not be total:
    keys that overlap (e.g. overlapping ``Period``s) may be mutually
    incomparable. Scans only require that domain streams are strictly
    ascending, so anything entirely past a probe stays past it.
    """

    def __lt__(self, other: Self, /) -> bool: ...


class Thunk[V]:
    """A computation the library calls when its value is needed.

    Seed thunks run when the head is demanded; value thunks run when the
    cell is demanded. The callable may return a value or an effect, e.g.
    ``Thunk(lambda: get(rule))``. Bare rules and callables in these slots
    remain data; subsequent unfold states are passed through unchanged.
    """

    __slots__ = ("fn",)

    def __init__(self, fn: Callable[[], Effect[V] | V]) -> None:
        self.fn = fn


@dataclass(frozen=True, slots=True)
class Cons[K: Key, V]:
    """One materialized node of a series' cell chain.

    ``tail`` resolves to the next node or ``None`` (exhaustion). Tails are
    ordinary rules: memoized per context and free to demand other rules,
    enabling value-dependent domains.
    """

    key: K
    value: Rule[V]
    tail: Rule[Cons[K, V] | None]


type Chain[K: Key, V] = Rule[Cons[K, V] | None]
type Pairs[K: Key, V] = Sequence[tuple[K, V | Thunk[V]]]
type UnfoldStep[S, K: Key, V] = Callable[
    [S],
    Effect[tuple[K, V | Thunk[V], S] | None] | tuple[K, V | Thunk[V], S] | None,
]
"""Produce a cell and next state from an unfold state, or end the chain."""

type QueryFn[K: Key, V, W] = Callable[[K, Chain[K, V]], Effect[W] | W]
"""Fold a query over a cell chain, with optional early termination."""

type Continuation[K: Key, V] = Callable[[Cons[K, V] | None], Chain[K, V]]
"""Build the chain that follows a base chain, given the base's last node
(``None`` when the base is empty)."""

type KeyMerge[K: Key] = Callable[[K, K], tuple[K, K | None, K | None]]
"""Merge two pending heads: the first tile of their union, then what remains
of each operand after it (``None`` when consumed). ``period_union`` and
``date_union`` are the canonical instances."""

type KeySplit[K: Key] = Callable[[K, K], tuple[K | None, K | None]]
"""Split a query at the end of a key into its inside and after parts.

The nonempty parts must partition the query in order, and the after part
must be entirely after the key. ``period_split`` and ``date_split`` are the
canonical instances. Also used to clip component keys at a preceding seam.
"""


class Series[K: Key, V, W](KeyedRule[K, W]):
    """A queryable series backed by an effectful cons-list built by unfold.

    ``K`` is both the cell key type and the query type. ``V`` is the cell
    value type and ``W`` the query answer type. ``name`` is optional; the
    constructors derive one when it is omitted.

    Raw cells are private: values are read only through the query, at any
    key or along ``walk``. A query must answer each cell key with that
    cell's value (as ``exact``, ``last``, ``accrue`` and ``covered`` do), so
    the cells are just the query's backing data.
    """

    def __init__(
        self, cells: Chain[K, V], query: QueryFn[K, V, W], *, name: str | None = None
    ) -> None:
        super().__init__(name)
        self._cells = cells
        self._query = query
        self._walk: Chain[K, W] | None = None

    def compute(self, q: K, /) -> Effect[W] | W:
        return self._query(q, self._cells)

    def walk(self) -> Chain[K, W]:
        """The cell keys as a lazy chain of this series' answers at each key.

        Walking reads only keys; a node's value queries the series at its
        key. The chain may be infinite, so stop at a key (``keys_until``) or
        on a value rather than walking to the end. Each value runs a full
        query, so walking ``n`` cells costs ``O(n²)`` scan steps for
        scanning queries. The chain is built once per series.
        """
        if self._walk is None:

            def answer(key: K, _value: Rule[V]) -> Thunk[W]:
                return Thunk(lambda: get_at(self, key))

            self._walk = map_cells(self._cells, answer, name=f"{self.name}.walk")
        return self._walk

    @classmethod
    @overload
    def unfold[S](
        cls,
        query: QueryFn[K, V, W],
        *,
        seed: Thunk[S],
        step: UnfoldStep[S, K, V],
        name: str | None = None,
    ) -> Series[K, V, W]: ...
    @classmethod
    @overload
    def unfold[S](
        cls,
        query: QueryFn[K, V, W],
        *,
        seed: S,
        step: UnfoldStep[S, K, V],
        name: str | None = None,
    ) -> Series[K, V, W]: ...
    @classmethod
    def unfold[S](
        cls,
        query: QueryFn[K, V, W],
        *,
        seed: S | Thunk[S],
        step: UnfoldStep[S, K, V],
        name: str | None = None,
    ) -> Series[K, V, W]:
        """Build a series by repeatedly applying ``step`` to an evolving state.

        A ``Thunk`` seed is resolved once by the head node before the first step.
        """
        name = _resolve_name(name, cls.__name__)
        return cls(unfold_cells(seed=seed, step=step, name=name), query, name=name)

    @classmethod
    def extend(
        cls,
        query: QueryFn[K, V, W],
        *,
        base: Chain[K, V],
        cont: Continuation[K, V],
        name: str | None = None,
    ) -> Series[K, V, W]:
        """Build a series that continues ``base`` lazily at its frontier."""
        name = _resolve_name(name, cls.__name__)
        return cls(extend_cells(base, cont, name=name), query, name=name)

    @classmethod
    def flatten(
        cls,
        components: Chain[int, Series[K, Any, W]],
        *,
        query: QueryFn[K, W, W],
        split_keys: KeySplit[K],
        name: str | None = None,
    ) -> Series[K, W, W]:
        """Flatten a lazy chain of series, preserving each component's query.

        Outer integer keys specify component order, not domain bounds. Walk
        the current component before requesting the next outer node: an
        infinite component leaves all following components untouched.

        A component owns queries through its last key; the next nonempty
        component owns the territory after it, including any gap before its
        first key. Empty or fully clipped components are skipped. The first
        and last nonempty components also answer before and after the spine.

        A query within one component delegates to it unchanged. A crossing
        query is partitioned at component seams and ``query`` folds a lazy
        chain of their answers, keyed by the respective subqueries. Use
        ``covered`` to sum period answers, or ``exact`` to reject crossing
        queries without reading their values. An empty composition is also
        answered by ``query``, over an empty chain.

        Cells hold component query answers, so raw component value types may
        differ. Overlapping continuation keys are clipped at the seam; their
        values query the original component on the clipped key. No component
        query is ever called with a replacement chain.

        Finite queries require only a finite prefix of each relevant domain
        (as with other ordered scans); an infinite prefix of empty components
        or keys that never advance past a query cannot produce an answer.
        """
        name = _resolve_name(name, cls.__name__)
        owners = _flatten_owners(name, components, split_keys)

        def answer(key: K, owner: Rule[_Component[K, W]]) -> Effect[W]:
            component = yield from get(owner)
            source = yield from get(component.value)
            return (yield from get_at(source, key))

        def value(key: K, owner: Rule[_Component[K, W]]) -> Thunk[W]:
            return Thunk(lambda: answer(key, owner))

        def part(
            state: tuple[K | None, Chain[K, _Component[K, W]]],
        ) -> Effect[tuple[K, Thunk[W], tuple[K | None, Chain[K, _Component[K, W]]]] | None]:
            remaining, cursor = state
            if remaining is None:
                return None
            node = yield from get(cursor)
            if node is None:
                return None
            owner = yield from get(node.value)
            while True:
                inside, after = split_keys(remaining, node.key)
                if after is None:
                    # Do not peek into the tail at an interior query endpoint.
                    return remaining, value(remaining, node.value), (None, node.tail)
                following = yield from get(node.tail)
                if following is None:
                    # The final component retains its own beyond-spine policy.
                    return remaining, value(remaining, node.value), (None, node.tail)
                next_owner = yield from get(following.value)
                if next_owner is not owner and inside is not None:
                    return inside, value(inside, node.value), (after, node.tail)
                node, owner = following, next_owner

        def compute(q: K, _cells: Chain[K, W]) -> Effect[W]:
            parts = unfold_cells(seed=(q, owners), step=part, name=f"{name}.parts@{q}")
            head = yield from get(parts)
            if head is not None and head.key == q:
                return (yield from get(head.value))
            return (yield from _as_effect(query(q, parts)))

        return cls(map_cells(owners, value, name=name), compute, name=name)

    @classmethod
    def of(
        cls,
        query: QueryFn[K, V, W],
        pairs: Pairs[K, V] | Rule[Pairs[K, V]],
        *,
        name: str | None = None,
    ) -> Series[K, V, W]:
        """Build a series from a sequence of pairs or a rule resolving one."""
        name = _resolve_name(name, cls.__name__)
        return cls(of_cells(pairs, name=name), query, name=name)

    @classmethod
    def empty(cls, query: QueryFn[K, V, W], *, name: str | None = None) -> Series[K, V, W]:
        """Build a series with no cells; ``query`` answers every key over the empty chain.

        With no cells to infer from, give the types explicitly, e.g.
        ``Series[Period, float, Maybe[float]].empty(query.accrue_drop(YF.cmonthly))``.
        """

        def step(_state: None) -> None:
            return None

        return cls.unfold(query, seed=None, step=step, name=name)

    @classmethod
    @overload
    def define[S](
        cls,
        query: QueryFn[K, V, W],
        *,
        seed: Thunk[S],
        name: str | None = None,
    ) -> Callable[[UnfoldStep[S, K, V]], Series[K, V, W]]: ...
    @classmethod
    @overload
    def define[S](
        cls,
        query: QueryFn[K, V, W],
        *,
        seed: S,
        name: str | None = None,
    ) -> Callable[[UnfoldStep[S, K, V]], Series[K, V, W]]: ...
    @classmethod
    def define[S](
        cls,
        query: QueryFn[K, V, W],
        *,
        seed: S | Thunk[S],
        name: str | None = None,
    ) -> Callable[[UnfoldStep[S, K, V]], Series[K, V, W]]:
        """Decorator form of ``unfold`` for self-referential series bodies.

        A ``Thunk`` seed is resolved once by the head node before the first step.
        Without a ``name``, the series is named after the decorated function.
        """

        def decorator(step: UnfoldStep[S, K, V]) -> Series[K, V, W]:
            step_name = _fn_name(step)
            label = name if name is not None or step_name is None else AutoName(step_name)
            return cls.unfold(query, seed=seed, step=step, name=label)

        return decorator


class _UnfoldRule[S, K: Key, V](Rule[Cons[K, V] | None]):
    """Rule that materializes one unfold node and its deferred tail."""

    def __init__(
        self,
        series_name: str,
        prev_key: K | None,
        state: S | Thunk[S],
        step: UnfoldStep[S, K, V],
    ) -> None:
        name = f"{series_name}.cells" if prev_key is None else f"{series_name}.tail@{prev_key}"
        super().__init__(name, structural=True)
        self._series_name = series_name
        self._prev_key = prev_key
        self._state = state
        self._unfold_step = step

    def compute(self) -> Effect[Cons[K, V] | None]:
        state = (
            (yield from _resolve_seed(self._state))
            if self._prev_key is None
            else cast(S, self._state)
        )
        result = yield from _as_effect(self._unfold_step(state))
        if result is None:
            return None
        key, value, next_state = result
        if self._prev_key is not None and not self._prev_key < key:
            raise ValueError(
                f"keys must be strictly ascending: got {self._prev_key!r} then {key!r}"
            )
        return Cons(
            key,
            Fn(_cell_fn(value), name=f"{self._series_name}@{key}", structural=True),
            _UnfoldRule(self._series_name, key, next_state, self._unfold_step),
        )


@overload
def unfold_cells[S, K: Key, V](
    *,
    seed: Thunk[S],
    step: UnfoldStep[S, K, V],
    name: str | None = None,
) -> Chain[K, V]: ...
@overload
def unfold_cells[S, K: Key, V](
    *,
    seed: S,
    step: UnfoldStep[S, K, V],
    name: str | None = None,
) -> Chain[K, V]: ...
def unfold_cells[S, K: Key, V](
    *,
    seed: S | Thunk[S],
    step: UnfoldStep[S, K, V],
    name: str | None = None,
) -> Chain[K, V]:
    """Build a standalone cell chain, e.g. for an ``extend_cells`` continuation.

    A ``Thunk`` seed is resolved once by the head node before the first step.
    """
    return _UnfoldRule(_resolve_name(name, "unfold_cells"), None, seed, step)


def of_cells[K: Key, V](
    pairs: Pairs[K, V] | Rule[Pairs[K, V]], *, name: str | None = None
) -> Chain[K, V]:
    """Build a standalone cell chain from a sequence of pairs or a rule resolving one."""

    def step(
        state: tuple[Pairs[K, V], int],
    ) -> tuple[K, V | Thunk[V], tuple[Pairs[K, V], int]] | None:
        source, index = state
        if index == len(source):
            return None
        key, value = source[index]
        return key, value, (source, index + 1)

    name = _resolve_name(name, "of_cells")
    if isinstance(pairs, Rule):

        def initial() -> Effect[tuple[Pairs[K, V], int]]:
            return (yield from get(pairs)), 0

        return unfold_cells(seed=Thunk(initial), step=step, name=name)
    return unfold_cells(seed=(pairs, 0), step=step, name=name)


def map_cells[K: Key, A, B](
    source: Chain[K, A],
    fn: Callable[[K, Rule[A]], B | Thunk[B]],
    *,
    name: str | None = None,
) -> Chain[K, B]:
    """Map cells one-for-one without forcing their values."""

    def step(cells: Chain[K, A]) -> Effect[tuple[K, B | Thunk[B], Chain[K, A]] | None]:
        node = yield from get(cells)
        if node is None:
            return None
        return node.key, fn(node.key, node.value), node.tail

    return unfold_cells(seed=source, step=step, name=_resolve_name(name, "map_cells"))


@overload
def scan_cells[K: Key, A, S, B](
    source: Chain[K, A],
    *,
    seed: Thunk[S],
    fn: Callable[[S, K, Rule[A]], tuple[B | Thunk[B], S]],
    name: str | None = None,
) -> Chain[K, B]: ...
@overload
def scan_cells[K: Key, A, S, B](
    source: Chain[K, A],
    *,
    seed: S,
    fn: Callable[[S, K, Rule[A]], tuple[B | Thunk[B], S]],
    name: str | None = None,
) -> Chain[K, B]: ...
def scan_cells[K: Key, A, S, B](
    source: Chain[K, A],
    *,
    seed: S | Thunk[S],
    fn: Callable[[S, K, Rule[A]], tuple[B | Thunk[B], S]],
    name: str | None = None,
) -> Chain[K, B]:
    """Map cells one-for-one while carrying structural accumulator state."""
    name = _resolve_name(name, "scan_cells")

    def step(
        state: tuple[Chain[K, A], S],
    ) -> Effect[tuple[K, B | Thunk[B], tuple[Chain[K, A], S]] | None]:
        cells, acc = state
        node = yield from get(cells)
        if node is None:
            return None
        value, next_acc = fn(acc, node.key, node.value)
        return node.key, value, (node.tail, next_acc)

    if isinstance(seed, Thunk):

        def head_seed() -> Effect[tuple[Chain[K, A], S]]:
            return source, (yield from _as_effect(seed.fn()))

        return unfold_cells(seed=Thunk[tuple[Chain[K, A], S]](head_seed), step=step, name=name)
    return unfold_cells(seed=(source, seed), step=step, name=name)


def extend_cells[K: Key, V](
    base: Chain[K, V],
    cont: Continuation[K, V],
    *,
    name: str | None = None,
) -> Chain[K, V]:
    """Continue ``base`` lazily with a chain built from its last node.

    Every base tail is wrapped by a rule that carries the node just emitted.
    When the wrapped tail is exhausted, ``cont`` receives that node (``None``
    for an empty base) and the wrapper resolves to the head of the returned
    chain, so nothing past the seam is wrapped. ``cont`` is invoked only when a
    walk reaches the base frontier, and no base tail is forced ahead of the
    walk, so a base tail may itself depend on the extended series at the key
    it just emitted.

    Keys must stay strictly ascending across the seam: a continuation whose
    first key is not entirely after the last base key raises ``ValueError``
    without forcing any cell.
    """
    name = _resolve_name(name, "extend_cells")

    def wrap(prev: Cons[K, V] | None, tail: Chain[K, V]) -> Chain[K, V]:
        def compute() -> Effect[Cons[K, V] | None]:
            node = yield from get(tail)
            if node is not None:
                return Cons(node.key, node.value, wrap(node, node.tail))
            node = yield from get(cont(prev))
            if node is not None and prev is not None and not prev.key < node.key:
                raise ValueError(
                    f"keys must be strictly ascending: got {prev.key!r} then {node.key!r}"
                )
            return node

        label = f"{name}.cells" if prev is None else f"{name}.tail@{prev.key}"
        return Fn(compute, name=label, structural=True)

    return wrap(None, base)


def concat_cells[J: Key, K: Key, V](
    outer: Chain[J, Chain[K, V]], *, name: str | None = None
) -> Chain[K, V]:
    """Concatenate a chain of chains in outer order; outer keys are discarded.

    Inner nodes pass through with their own value rules. An outer value is read
    only when the walk exhausts the chain before it, so an infinite inner chain
    leaves later outer values untouched.

    Keys must stay strictly ascending across the concatenation. Nothing is
    clipped: a key that is not entirely after the previous one raises
    ``ValueError`` when the walk reaches it. Gaps are allowed and are answered
    by the query of the series built over the result.
    """
    name = _resolve_name(name, "concat_cells")

    def walk(
        prev: Cons[K, V] | None, rest: Chain[J, Chain[K, V]], inner: Chain[K, V] | None
    ) -> Chain[K, V]:
        def compute() -> Effect[Cons[K, V] | None]:
            remaining, cells = rest, inner
            while True:
                if cells is None:
                    head = yield from get(remaining)
                    if head is None:
                        return None
                    cells = yield from get(head.value)
                    remaining = head.tail
                node = yield from get(cells)
                if node is None:
                    cells = None
                    continue
                if prev is not None and not prev.key < node.key:
                    raise ValueError(
                        f"keys must be strictly ascending: got {prev.key!r} then {node.key!r}"
                    )
                return Cons(node.key, node.value, walk(node, remaining, node.tail))

        label = f"{name}.cells" if prev is None else f"{name}.tail@{prev.key}"
        return Fn(compute, name=label, structural=True)

    return walk(None, outer, None)


def flat_map_cells[J: Key, A, K: Key, V](
    outer: Chain[J, A],
    fn: Callable[[A], Chain[K, V]],
    *,
    name: str | None = None,
) -> Chain[K, V]:
    """Map each outer value to a chain and concatenate them: ``concat ∘ map``.

    ``fn`` receives the resolved value, since the resulting structure depends on
    it. See ``concat_cells`` for laziness and key ordering.
    """
    name = _resolve_name(name, "flat_map_cells")

    def chain(_key: J, value: Rule[A]) -> Thunk[Chain[K, V]]:
        def build() -> Effect[Chain[K, V]]:
            return fn((yield from get(value)))

        return Thunk(build)

    return concat_cells(map_cells(outer, chain, name=f"{name}.chains"), name=name)


def _clip_period(key: Period, start: date | None, end: date | None) -> Period | None:
    """The part of ``key`` within ``(start, end]``, or ``None`` if they don't overlap."""
    lo = key.start if start is None else max(key.start, start)
    hi = key.end if end is None else min(key.end, end)
    return Period(lo, hi) if lo < hi else None


def clip_periods[V, W](
    source: Series[Period, V, W],
    start: date | None = None,
    end: date | None = None,
    *,
    outside: Maybe[W] = Na,
    name: str | None = None,
) -> Series[Period, W, Maybe[W]]:
    """``source`` within ``(start, end]``; either bound may be open.

    A query is trimmed to the bounds and forwarded to ``source``, so time outside
    them is left out; a query entirely outside answers ``outside``. Give a value
    only when it is what the window means, e.g. ``0.0`` for a flow that stops at
    the window; a gap inside the bounds still gets ``source``'s answer. Cells are ``source``'s
    cells trimmed to the bounds, each holding ``source``'s answer for its trimmed
    period, so concatenations agree with direct queries. Cells before ``start``
    are skipped and the walk stops at the first cell starting at or after ``end``,
    reading keys only.
    """
    name = name if name is not None else derived_name("clip_periods", source)

    def answer(key: Period) -> Thunk[W]:
        return Thunk(lambda: get_at(source, key))

    def step(
        cells: Chain[Period, V],
    ) -> Effect[tuple[Period, Thunk[W], Chain[Period, V]] | None]:
        node = yield from get(cells)
        while node is not None:
            if end is not None and end <= node.key.start:
                return None
            key = _clip_period(node.key, start, end)
            if key is not None:
                return key, answer(key), node.tail
            node = yield from get(node.tail)
        return None

    def compute(q: Period, _cells: Chain[Period, W]) -> Effect[Maybe[W]]:
        inside = _clip_period(q, start, end)
        if inside is None:
            return outside
        return (yield from get_at(source, inside))

    return Series(unfold_cells(seed=source._cells, step=step, name=name), compute, name=name)


def clip_dates[V, W](
    source: Series[date, V, W],
    start: date | None = None,
    end: date | None = None,
    *,
    outside: Maybe[W] = Na,
    name: str | None = None,
) -> Series[date, V, Maybe[W]]:
    """``source`` within ``(start, end]``; either bound may be open.

    Cells are ``source``'s cells within the bounds, passed through with their own
    value rules. A query inside the bounds is answered by ``source``'s query over
    those cells, so a look-back query such as ``last`` cannot reach a cell before
    ``start``; a query outside the bounds answers ``outside``. Cells before ``start`` are
    skipped and the walk stops at the first cell after ``end``, reading keys only.
    """
    name = name if name is not None else derived_name("clip_dates", source)

    def inside(key: date) -> bool:
        return (start is None or start < key) and (end is None or key <= end)

    def walk(prev: date | None, rest: Chain[date, V]) -> Chain[date, V]:
        def compute() -> Effect[Cons[date, V] | None]:
            node = yield from get(rest)
            while node is not None and start is not None and node.key <= start:
                node = yield from get(node.tail)
            if node is None or not inside(node.key):
                return None
            return Cons(node.key, node.value, walk(node.key, node.tail))

        label = f"{name}.cells" if prev is None else f"{name}.tail@{prev}"
        return Fn(compute, name=label, structural=True)

    def query(q: date, cells: Chain[date, V]) -> Effect[Maybe[W]]:
        if not inside(q):
            return outside
        return (yield from _as_effect(source._query(q, cells)))

    return Series(walk(None, source._cells), query, name=name)


type _Continued[K: Key, W] = tuple[int, Series[K, Any, W] | None, Cons[K, W] | None]
"""Next outer index, the component just emitted (``None`` before ``base``), and
the last walk node seen so far across emitted components."""


def continue_series[K: Key, W](
    base: Series[K, Any, W],
    *conts: Callable[[Cons[K, W] | None], Series[K, Any, W] | None],
    name: str | None = None,
) -> Chain[int, Series[K, Any, W]]:
    """Build ``[base, conts[0](last), conts[1](last), ...]`` for ``Series.flatten``.

    Each continuation receives the last walk node so far: the last node of
    the previous component's ``walk()``, whose value is that component's
    answer at its last key. An empty component passes on the node before it,
    so ``None`` means every earlier component, ``base`` included, was empty.
    A continuation returns the next series, or ``None`` to end the chain
    there; later continuations are then never called.

    A continuation runs when its outer node is requested and is memoized per
    context; reading the first outer node does not inspect the base, and the
    tail after the last continuation ends without walking anything. Flatten
    only requests an outer tail after the preceding component ends, so an
    infinite component never invokes the continuations after it. Direct
    callers must obey the same discipline: requesting an outer tail itself
    exhausts the component before it, whose end may depend on other rules.
    """

    def step(
        state: _Continued[K, W],
    ) -> Effect[tuple[int, Series[K, Any, W], _Continued[K, W]] | None]:
        index, prior, last = state
        if prior is None:
            return 0, base, (1, base, None)
        if index > len(conts):
            return None
        node = yield from get(prior.walk())
        while node is not None:
            last = node
            node = yield from get(node.tail)
        following = conts[index - 1](last)
        if following is None:
            return None
        return index, following, (index + 1, following, last)

    name = name if name is not None else derived_name("continue_series", base)
    return unfold_cells(seed=(0, None, None), step=step, name=name)


type _Component[K: Key, W] = Cons[int, Series[K, Any, W]]
type _FlattenState[K: Key, W] = tuple[
    Chain[int, Series[K, Any, W]], _Component[K, W] | None, Chain[K, Any] | None, K | None
]


def _flatten_owners[K: Key, W](
    name: str,
    components: Chain[int, Series[K, Any, W]],
    split_keys: KeySplit[K],
) -> Chain[K, _Component[K, W]]:
    """A shared flatmap walk: each emitted key retains its outer owner node.

    Owner identity marks a seam, including when a source object is reused.
    Both flattened cells and query routing walk this memoized chain. Only
    structural rules are read; source values remain behind source queries.
    """

    def step(
        state: _FlattenState[K, W],
    ) -> Effect[tuple[K, _Component[K, W], _FlattenState[K, W]] | None]:
        outer, owner, inner, previous = state
        while True:
            if owner is None:
                owner = yield from get(outer)
                if owner is None:
                    return None
                source = yield from get(owner.value)
                inner = source._cells
            assert inner is not None
            node = yield from get(inner)
            if node is None:
                outer, owner, inner = owner.tail, None, None
                continue
            key = node.key if previous is None else split_keys(node.key, previous)[1]
            inner = node.tail
            if key is not None:
                return key, owner, (outer, owner, inner, key)

    return unfold_cells(seed=(components, None, None, None), step=step, name=f"{name}.owners")


type _Frontier[K: Key] = tuple[K | None, Chain[K, Any] | None]
"""One merge operand: pending head not yet emitted past, and the rest of its
chain. ``(None, tail)`` needs a refill; ``(None, None)`` is exhausted."""


def merge_cells[K: Key, V](
    chains: Sequence[Chain[K, Any]],
    merge: KeyMerge[K],
    cell: Callable[[K], V | Thunk[V]],
    *,
    name: str | None = None,
) -> Chain[K, V]:
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
    ) -> Effect[tuple[K, V | Thunk[V], tuple[_Frontier[K], ...]] | None]:
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
    return unfold_cells(seed=seed, step=step, name=_resolve_name(name, "merge_cells"))


def _resolve_name(name: str | None, kind: str) -> str:
    """``name`` if given, else a fresh ``kind#n`` label for structural rules to extend."""
    return name if name is not None else auto_name(kind)


def _cell_fn[V](value: V | Thunk[V]) -> Callable[[], Effect[V] | V]:
    if isinstance(value, Thunk):
        return value.fn
    if isinstance(value, Generator):
        raise TypeError(
            "live generator as a cell value; wrap the computation in Thunk(lambda: ...)"
        )
    return lambda value=value: value


def _resolve_seed[S](seed: S | Thunk[S]) -> Effect[S]:
    if isinstance(seed, Thunk):
        return (yield from _as_effect(seed.fn()))
    return seed


def _as_effect[V](value: Effect[V] | V) -> Effect[V]:
    """Normalize plain and generator return values to an ``Effect``."""
    if isinstance(value, Generator):
        return value

    def completed() -> Effect[V]:
        if False:
            yield
        return value

    return completed()


def keys_until[K: Key, V](cells: Chain[K, V], stop: K) -> Effect[list[K]]:
    """Collect keys through ``stop`` without forcing cells or a past frontier."""
    keys: list[K] = []
    node = yield from get(cells)
    while node is not None:
        if stop < node.key:
            break
        keys.append(node.key)
        node = yield from get(node.tail)
    return keys
