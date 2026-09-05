# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from collections.abc import Callable, Generator, Hashable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, Self

from orcaset.rule import Cell, Effect, KeyedRule, Rule, get, get_at


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
    cell: Rule[V]
    tail: Rule[Cons[K, V] | None]


type Cells[K: Key, V] = Rule[Cons[K, V] | None]
type UnfoldStep[S, K: Key, V] = Callable[
    [S],
    Effect[tuple[K, V | Thunk[V], S] | None] | tuple[K, V | Thunk[V], S] | None,
]
"""Produce a cell and next state from an unfold state, or end the chain."""

type QueryFn[K: Key, V, W] = Callable[[K, Cells[K, V]], Effect[W] | W]
"""Fold a query over a cell chain, with optional early termination."""

type Continuation[K: Key, V] = Callable[[Cons[K, V] | None], Cells[K, V]]
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

    def compute(self, q: K, /) -> Effect[W]:
        return (yield from _as_effect(self._query(q, self._cells)))

    @classmethod
    def unfold[S](
        cls,
        name: str,
        query: QueryFn[K, V, W],
        *,
        seed: S,
        step: UnfoldStep[S, K, V],
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
        cont: Continuation[K, V],
    ) -> Series[K, V, W]:
        """Build a series that continues ``base`` lazily at its frontier."""
        return cls(name, extend_cells(name, base, cont), query)

    @classmethod
    def flatten(
        cls,
        name: str,
        components: Cells[int, Series[K, Any, W]],
        *,
        query: QueryFn[K, W, W],
        split_keys: KeySplit[K],
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
        owners = _flatten_owners(name, components, split_keys)

        def answer(key: K, owner: Rule[_Component[K, W]]) -> Effect[W]:
            component = yield from get(owner)
            source = yield from get(component.cell)
            return (yield from get_at(source, key))

        def value(key: K, owner: Rule[_Component[K, W]]) -> Thunk[W]:
            return Thunk(lambda: answer(key, owner))

        def part(
            state: tuple[K | None, Cells[K, _Component[K, W]]],
        ) -> Effect[tuple[K, Thunk[W], tuple[K | None, Cells[K, _Component[K, W]]]] | None]:
            remaining, cursor = state
            if remaining is None:
                return None
            node = yield from get(cursor)
            if node is None:
                return None
            owner = yield from get(node.cell)
            while True:
                inside, after = split_keys(remaining, node.key)
                if after is None:
                    # Do not peek into the tail at an interior query endpoint.
                    return remaining, value(remaining, node.cell), (None, node.tail)
                following = yield from get(node.tail)
                if following is None:
                    # The final component retains its own beyond-spine policy.
                    return remaining, value(remaining, node.cell), (None, node.tail)
                next_owner = yield from get(following.cell)
                if next_owner is not owner and inside is not None:
                    return inside, value(inside, node.cell), (after, node.tail)
                node, owner = following, next_owner

        def compute(q: K, _cells: Cells[K, W]) -> Effect[W]:
            parts = unfold_cells(f"{name}.parts@{q}", seed=(q, owners), step=part)
            head = yield from get(parts)
            if head is not None and head.key == q:
                return (yield from get(head.cell))
            return (yield from _as_effect(query(q, parts)))

        return cls(name, map_cells(name, owners, value), compute)

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
    ) -> Callable[[UnfoldStep[S, K, V]], Series[K, V, W]]:
        """Decorator form of ``unfold`` for self-referential series bodies."""

        def decorator(step: UnfoldStep[S, K, V]) -> Series[K, V, W]:
            return cls.unfold(name, query, seed=seed, step=step)

        return decorator


class _UnfoldRule[S, K: Key, V](Rule[Cons[K, V] | None]):
    """Rule that materializes one unfold node and its deferred tail."""

    def __init__(
        self,
        series_name: str,
        prev_key: K | None,
        state: S,
        step: UnfoldStep[S, K, V],
    ) -> None:
        name = f"{series_name}.cells" if prev_key is None else f"{series_name}.tail@{prev_key}"
        super().__init__(name, structural=True)
        self._series_name = series_name
        self._prev_key = prev_key
        self._state = state
        self._unfold_step = step

    def compute(self) -> Effect[Cons[K, V] | None]:
        result = yield from _as_effect(self._unfold_step(self._state))
        if result is None:
            return None
        key, value, next_state = result
        if self._prev_key is not None and not self._prev_key < key:
            raise ValueError(
                f"keys must be strictly ascending: got {self._prev_key!r} then {key!r}"
            )
        return Cons(
            key,
            Cell(f"{self._series_name}@{key}", _cell_fn(value), structural=True),
            _UnfoldRule(self._series_name, key, next_state, self._unfold_step),
        )


def unfold_cells[S, K: Key, V](
    name: str,
    *,
    seed: S,
    step: UnfoldStep[S, K, V],
) -> Cells[K, V]:
    """Build a standalone cell chain, e.g. for an ``extend_cells`` continuation."""
    return _UnfoldRule(name, None, seed, step)


def map_cells[K: Key, A, B](
    name: str,
    source: Cells[K, A],
    fn: Callable[[K, Rule[A]], B | Thunk[B]],
) -> Cells[K, B]:
    """Map cells one-for-one without forcing their values."""

    def step(cells: Cells[K, A]) -> Effect[tuple[K, B | Thunk[B], Cells[K, A]] | None]:
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
    ) -> Effect[tuple[K, B | Thunk[B], tuple[Cells[K, A], S]] | None]:
        cells, acc = state
        node = yield from get(cells)
        if node is None:
            return None
        value, next_acc = fn(acc, node.key, node.cell)
        return node.key, value, (node.tail, next_acc)

    return unfold_cells(name, seed=(source, seed), step=step)


def extend_cells[K: Key, V](
    name: str,
    base: Cells[K, V],
    cont: Continuation[K, V],
) -> Cells[K, V]:
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

    def wrap(prev: Cons[K, V] | None, tail: Cells[K, V]) -> Cells[K, V]:
        def compute() -> Effect[Cons[K, V] | None]:
            node = yield from get(tail)
            if node is not None:
                return Cons(node.key, node.cell, wrap(node, node.tail))
            node = yield from get(cont(prev))
            if node is not None and prev is not None and not prev.key < node.key:
                raise ValueError(
                    f"keys must be strictly ascending: got {prev.key!r} then {node.key!r}"
                )
            return node

        label = f"{name}.cells" if prev is None else f"{name}.tail@{prev.key}"
        return Cell(label, compute, structural=True)

    return wrap(None, base)


def continue_series[K: Key, V, W](
    name: str,
    base: Series[K, V, W],
    cont: Callable[[Cons[K, V] | None], Series[K, Any, W]],
) -> Cells[int, Series[K, Any, W]]:
    """Build ``[base, lazy cont(last)]`` for ``Series.flatten``.

    ``cont`` receives the last raw base node, or ``None`` if empty. Its
    construction is memoized per context; reading the first outer node does
    not inspect the base. Flatten only requests the outer tail after the
    base ends, so an infinite base never constructs its continuation. Direct
    callers must obey the same discipline: requesting this outer tail itself
    exhausts the base, whose end may depend on other rules.
    """

    def step(
        index: int,
    ) -> Effect[tuple[int, Series[K, Any, W] | Thunk[Series[K, Any, W]], int] | None]:
        if index == 0:
            return 0, base, 1
        if index != 1:
            return None
        last: Cons[K, V] | None = None
        node = yield from get(base.cells)
        while node is not None:
            last = node
            node = yield from get(node.tail)
        return 1, Thunk(lambda: cont(last)), 2

    return unfold_cells(name, seed=0, step=step)


type _Component[K: Key, W] = Cons[int, Series[K, Any, W]]
type _FlattenState[K: Key, W] = tuple[
    Cells[int, Series[K, Any, W]], _Component[K, W] | None, Cells[K, Any] | None, K | None
]


def _flatten_owners[K: Key, W](
    name: str,
    components: Cells[int, Series[K, Any, W]],
    split_keys: KeySplit[K],
) -> Cells[K, _Component[K, W]]:
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
                source = yield from get(owner.cell)
                inner = source.cells
            assert inner is not None
            node = yield from get(inner)
            if node is None:
                outer, owner, inner = owner.tail, None, None
                continue
            key = node.key if previous is None else split_keys(node.key, previous)[1]
            inner = node.tail
            if key is not None:
                return key, owner, (outer, owner, inner, key)

    return unfold_cells(f"{name}.owners", seed=(components, None, None, None), step=step)


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
    return unfold_cells(name, seed=seed, step=step)


def _cell_fn[V](value: V | Thunk[V]) -> Callable[[], Effect[V] | V]:
    if isinstance(value, Thunk):
        return value.fn
    if isinstance(value, Generator):
        raise TypeError(
            "live generator as a cell value; wrap the computation in Thunk(lambda: ...)"
        )
    return lambda value=value: value


def _as_effect[V](value: Effect[V] | V) -> Effect[V]:
    """Normalize plain and generator return values to an ``Effect``."""
    if isinstance(value, Generator):
        return value

    def completed() -> Effect[V]:
        if False:
            yield
        return value

    return completed()


def keys_until[K: Key, V](cells: Cells[K, V], stop: K) -> Effect[list[K]]:
    """Collect keys through ``stop`` without forcing cells or a past frontier."""
    keys: list[K] = []
    node = yield from get(cells)
    while node is not None:
        if stop < node.key:
            break
        keys.append(node.key)
        node = yield from get(node.tail)
    return keys
