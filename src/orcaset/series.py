# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Line-item series over the free monad core.

A :class:`Series` is a financial line item: something you can ask a question
of. :meth:`Series.query` is the sole retrieval interface and it is total —
any query may be asked of any series — so it answers ``F[Maybe[V]]``: a lazy
value that may be :data:`~orcaset.maybe.MISSING`.

There are two kinds of series:

- :class:`LeafSeries` holds cells and a convention. Its stream is an ordered
  run of ``(key, F[value])`` pairs; ``select`` narrows that stream to the
  pairs answering a query and ``reduce`` collapses them to one answer. A cell
  exists only where data exists, so absence is positional and ``reduce`` must
  be total: an empty selection still has to produce an answer (usually
  ``MISSING``).
- :class:`MapSeries`, :class:`Map2Series` and :class:`MapNSeries` are
  *views*: they have no cells and no convention. They transform and combine
  complete answers, so their provenance is the child query nodes rather than
  selected cells. Evidence — the ``select`` audit view — exists only at
  leaves, which is exactly where the arithmetic on cells happens.

:func:`resample` bridges back: it tabulates any series at a new key grid,
producing a leaf whose cells are the source's query nodes. That is how a
monthly line becomes an annual one, and how a view regains cells.

Identity is what makes caching correct:

- Each series memoizes one node per question — ``query(q)``, ``select(q)``,
  ``keys()`` — keyed by query equality, so every reference to the same
  question is the same graph node. Construct a series once per model and
  share it by reference; never rebuild the same logical series.
- Series memoize *nodes*, never values. Values are cached per
  :class:`~orcaset.context.Context`; evaluating in a fresh context re-runs
  cell factories from scratch.

Key discipline (enforced as a stream is pulled): keys are hashable and
totally ordered, each stream yields keys in strictly increasing order, and
queries are hashable and immutable. Select, reduce and view functions must be
deterministic, must never evaluate nodes (no ``run``), and should return
original cell nodes on trivial paths (an unclipped pair, a fold of one) so
shared cells stay shared graph nodes.

Recursive definitions query the series being defined: a cell references
``series.query(prior_window)`` for whatever it depends on, so dependencies are
stated in key terms rather than stream positions and survive re-keying. Such a
cell receives a ``Maybe`` and must resolve it — seeding on ``MISSING`` is how
a recursion states its base case. Standard conventions live in
:mod:`orcaset.conventions`; absence policies in :mod:`orcaset.maybe`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Iterator, Sequence
from typing import Protocol, Self

from .context import Context
from .f import Delay, F, Pure
from .maybe import Maybe, Missing


class Key(Protocol):
    """A series key: totally ordered within a stream, and hashable.

    Only ``<`` is required. Hashability cannot be expressed here but is
    assumed — cells are indexed by key.
    """

    def __lt__(self, other: Self, /) -> bool: ...


def lift2[A, B, W](f: Callable[[A, B], W], fa: F[A], fb: F[B], *, label: str | None = None) -> F[W]:
    """Combine two nodes pointwise. Parameters keep closures loop-safe."""
    return fa.bind(lambda a: fb.map(lambda b: f(a, b)), label=label)


# Replayable iterables ------------------------------------------------------


class Replay[T]:
    """Buffered replay of one materialization of a one-shot iterable.

    Items are pulled on demand and buffered, so the underlying iterator is
    advanced at most once per position. A ``Replay`` is per-context state: it
    lives in a context cache as the value of a graph node. Construct one only
    inside an ``F`` node's evaluation, or over already-realized immutable
    data; never share a ``Replay`` over a generator across contexts.
    """

    __slots__ = ("_exhausted", "_items", "_iter")

    def __init__(self, source: Iterable[T]) -> None:
        self._items: list[T] = []
        self._iter: Iterator[T] = iter(source)
        self._exhausted: bool = False

    def __iter__(self) -> Iterator[T]:
        i = 0
        while True:
            if i >= len(self._items) and not self._pull():
                return
            yield self._items[i]
            i += 1

    def _pull(self) -> bool:
        if self._exhausted:
            return False
        try:
            item = next(self._iter)
        except StopIteration:
            self._exhausted = True
            return False
        self._accept(item)
        return True

    def _accept(self, item: T) -> None:
        self._items.append(item)


class CellReplay[K: Key, V](Replay[tuple[K, F[V]]]):
    """Replay of a series stream: cells, key-ordered and key-indexed.

    Keys are checked for strict increase and comparability as the stream is
    pulled, so a misordered stream fails loudly rather than silently
    answering the wrong question.
    """

    __slots__ = ("_index",)

    def __init__(self, source: Iterable[tuple[K, F[V]]]) -> None:
        super().__init__(source)
        self._index: dict[K, F[V]] = {}

    def _accept(self, item: tuple[K, F[V]]) -> None:
        key, cell = item
        if self._items:
            prev = self._items[-1][0]
            try:
                ordered = prev < key
            except TypeError:
                raise ValueError(
                    f"series keys must be strictly increasing and comparable: "
                    f"{prev!r} not comparable to {key!r}"
                ) from None
            if not ordered:
                raise ValueError(f"series keys must be strictly increasing: {prev!r} then {key!r}")
        self._items.append(item)
        if key not in self._index:
            self._index[key] = cell

    def find(self, key: K) -> F[V]:
        """Return the cell at ``key``, pulling the stream forward as needed.

        Hash-indexed: repeated lookups are O(1) once the stream has been
        pulled through ``key``. Raises ``KeyError`` if the stream passes or
        exhausts without yielding ``key``.
        """
        cell = self._index.get(key)
        if cell is not None:
            return cell
        while not self._items or self._items[-1][0] < key:
            if not self._pull():
                break
            if self._items[-1][0] == key:
                return self._index[key]
        raise KeyError(key)


type Cell[K, V] = tuple[K, F[V]]
"""One ``(key, value node)`` pair. A cell exists only where data exists."""

type Cells[K, V] = Iterable[Cell[K, V]]
"""An ordered run of cells, strictly increasing in key."""

type Stream[K: Key, V] = F[CellReplay[K, V]]
"""The node whose per-context value is a leaf's materialized cells.

A ``Delay`` for a leaf built from a cell factory; a ``Map``/``Bind`` when the
grid is derived from another series.
"""

type Keys[K] = F[Replay[K]]
"""The node whose per-context value is a series' key sequence."""


type Select[K: Key, V, Q] = Callable[[CellReplay[K, V], Q], tuple[Cell[K, V], ...]]
"""Narrow a stream to the (possibly clipped) cells answering ``Q``.

Pure and deterministic: may transform keys and construct new cell nodes as
data (e.g. scale a partial period) but must never evaluate them, and must
return original cell nodes when no transformation applies. Out of coverage it
returns ``()`` rather than raising — the answer to "nothing here" is
``reduce``'s to give. Coverage and gap policy live here; the output is the
complete, self-describing evidence handed to ``Reduce``.
"""

type Reduce[K, V] = Callable[[tuple[Cell[K, V], ...]], F[Maybe[V]]]
"""Collapse selected cells to a single answer node.

Pure, deterministic, and **total**: it is handed ``()`` whenever a query
falls outside coverage and must still answer — usually
:data:`~orcaset.maybe.MISSING_NODE`, or a declared neutral value for
conventions where emptiness has a meaning (no activity in a window is zero
flow). Returns the lone cell untouched when reducing a single pair.
"""


# Series --------------------------------------------------------------------


class Series[K: Key, V, Q = K](ABC):
    """A queryable financial line item whose answer may be absent.

    Subclasses supply unmemoized node builders; the base owns the memo
    discipline, so there is exactly one ``keys()`` node and one ``query(q)``
    node per series, forever, keyed by query equality. ``Q`` must be hashable
    and immutable.
    """

    __slots__ = ("_keys", "_queries", "label")

    label: str

    def __init__(self, *, label: str) -> None:
        self.label = label
        self._queries: dict[Q, F[Maybe[V]]] = {}
        self._keys: Keys[K] | None = None

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.label!r})"

    @abstractmethod
    def _keys_node(self) -> Keys[K]:
        """Build the key node. Called at most once; see :meth:`keys`."""

    @abstractmethod
    def _query_node(self, q: Q) -> F[Maybe[V]]:
        """Build the answer node for ``q``. Called at most once per ``q``."""

    def keys(self) -> Keys[K]:
        """The key sequence of this series: one shared node, replayable per context."""
        if self._keys is None:
            self._keys = self._keys_node()
        return self._keys

    def query(self, q: Q) -> F[Maybe[V]]:
        """The answer to ``q``: one shared node per ``(series, query)``.

        Total — every query has an answer node, which may evaluate to
        :data:`~orcaset.maybe.MISSING`. Evaluation forces only what the
        answer depends on.
        """
        node = self._queries.get(q)
        if node is None:
            node = self._query_node(q)
            self._queries[q] = node
        return node

    def map_maybe[W](self, fn: Callable[[Maybe[V]], Maybe[W]], *, label: str) -> Series[K, W, Q]:
        """View this series through ``fn``, which sees absence and decides.

        The primitive view: ``fn`` receives the complete answer — value or
        ``MISSING`` — and returns the transformed answer. It must be
        deterministic and must not evaluate nodes.
        """
        return MapSeries(self, fn, label=label)

    def map[W](self, fn: Callable[[V], W], *, label: str) -> Series[K, W, Q]:
        """View this series through ``fn``, propagating absence.

        Sugar for the common case: ``fn`` sees values only, and an absent
        answer stays absent.
        """
        return self.map_maybe(
            lambda answer: answer if isinstance(answer, Missing) else fn(answer), label=label
        )

    def fill(self, default: V, *, label: str | None = None) -> Series[K, V, Q]:
        """View this series with absent answers replaced by ``default``."""
        return self.map_maybe(
            lambda answer: default if isinstance(answer, Missing) else answer,
            label=label if label is not None else f"{self.label} (fill {default!r})",
        )

    def items(self: Series[K, V, K], ctx: Context) -> Iterator[tuple[K, F[Maybe[V]]]]:
        """Enumerate this series' keys with their point answers.

        Defined only where a key is a valid query. Materializes the key
        sequence in ``ctx``; the answers stay lazy.
        """
        for key in self.keys().run(ctx):
            yield key, self.query(key)


class LeafSeries[K: Key, V, Q = K](Series[K, V, Q]):
    """A line item defined by cells plus a select/reduce convention.

    The only kind of series with evidence: :meth:`select` is the audit view
    behind :meth:`~Series.query`.
    """

    __slots__ = ("_reduce", "_select", "_selects", "_stream")

    def __init__(
        self,
        stream: Stream[K, V],
        select: Select[K, V, Q],
        reduce: Reduce[K, V],
        *,
        label: str,
    ) -> None:
        super().__init__(label=label)
        self._stream: Stream[K, V] = stream
        self._select = select
        self._reduce = reduce
        self._selects: dict[Q, F[tuple[Cell[K, V], ...]]] = {}

    @classmethod
    def from_cells(
        cls,
        cells: Callable[[], Cells[K, V]],
        select: Select[K, V, Q],
        reduce: Reduce[K, V],
        *,
        label: str,
    ) -> Self:
        """Define a series from a factory of ``(key, cell)`` pairs.

        The factory runs once per context. It may reference the series being
        defined, or any other series, through ``query`` — nodes are inert
        until evaluated. It must be deterministic and must not evaluate its
        own cells. A recursive cell receives a ``Maybe`` answer and must
        resolve it; a cell that cannot should not be yielded at all, since
        absence in a stream is the absence of a cell.
        """
        return cls(
            Delay(lambda: CellReplay(cells()), label=label),
            select,
            reduce,
            label=label,
        )

    @classmethod
    def from_pairs(
        cls,
        pairs: Iterable[tuple[K, V]],
        select: Select[K, V, Q],
        reduce: Reduce[K, V],
        *,
        label: str,
    ) -> Self:
        """Define an input series from plain ``(key, value)`` pairs.

        Values are lifted with ``Pure`` once at construction, so input cells
        are model-owned nodes shared across contexts.
        """
        items: list[Cell[K, V]] = [(key, Pure(value)) for key, value in pairs]
        return cls.from_cells(lambda: items, select, reduce, label=label)

    def select(self, q: Q) -> F[tuple[Cell[K, V], ...]]:
        """The selection ``Label.select[q]``: one shared node per ``(series, query)``.

        Evaluates to the (possibly clipped) cells that answer ``q`` — the
        evidence behind :meth:`~Series.query`. Cells stay lazy; run them in
        the same context to see the values they contribute.
        """
        node = self._selects.get(q)
        if node is None:
            sel = self._select
            node = self._stream.map(
                lambda replay: sel(replay, q), label=f"{self.label}.select[{q}]"
            )
            self._selects[q] = node
        return node

    def _query_node(self, q: Q) -> F[Maybe[V]]:
        red = self._reduce
        label = f"{self.label}[{q}]"

        def reduce_pairs(pairs: tuple[Cell[K, V], ...]) -> F[Maybe[V]]:
            try:
                return red(pairs)
            except Exception as err:
                err.add_note(f"while reducing {label}")
                raise

        return self.select(q).bind(reduce_pairs, label=label)

    def _keys_node(self) -> Keys[K]:
        return self._stream.map(
            lambda replay: Replay(key for key, _ in replay), label=f"{self.label}.keys"
        )

    def stream(self, ctx: Context) -> CellReplay[K, V]:
        """Materialize this leaf's cells in ``ctx``.

        The raw stream, for inspection and testing; :meth:`~Series.query` is
        the modelling interface.
        """
        return self._stream.run(ctx)


# Views ---------------------------------------------------------------------


class MapSeries[K: Key, V, W, Q = K](Series[K, W, Q]):
    """A view that transforms complete answers from another series.

    No cells and no convention of its own: its query nodes retain the source
    query — and therefore the source selection — as a dependency, and it
    shares the source's key node.
    """

    __slots__ = ("_fn", "_source")

    def __init__(
        self,
        source: Series[K, V, Q],
        fn: Callable[[Maybe[V]], Maybe[W]],
        *,
        label: str,
    ) -> None:
        super().__init__(label=label)
        self._source = source
        self._fn = fn

    def _keys_node(self) -> Keys[K]:
        return self._source.keys()

    def _query_node(self, q: Q) -> F[Maybe[W]]:
        fn = self._fn
        label = f"{self.label}[{q}]"

        def apply(answer: Maybe[V]) -> Maybe[W]:
            try:
                return fn(answer)
            except Exception as err:
                err.add_note(f"while mapping {label}")
                raise

        return self._source.query(q).map(apply, label=label)


class Map2Series[K: Key, A, B, W, Q = K](Series[K, W, Q]):
    """A view combining two series' answers pointwise.

    Both sources are asked *every* query, including where they have no
    coverage, so ``fn`` sees ``MISSING`` on either side and states the policy
    — see :func:`~orcaset.maybe.strict`, :func:`~orcaset.maybe.propagate` and
    :func:`~orcaset.maybe.fill`. Keys are the ordered union of the sources'
    keys.

    Both sources must interpret ``Q`` the same way: combining a windowed flow
    with a point balance at the same query is type-correct and meaningless.
    """

    __slots__ = ("_a", "_b", "_fn")

    def __init__(
        self,
        a: Series[K, A, Q],
        b: Series[K, B, Q],
        fn: Callable[[Maybe[A], Maybe[B]], Maybe[W]],
        *,
        label: str,
    ) -> None:
        super().__init__(label=label)
        self._a = a
        self._b = b
        self._fn = fn

    def _keys_node(self) -> Keys[K]:
        return self._a.keys().bind(
            lambda ka: self._b.keys().map(lambda kb: Replay(ordered_union((ka, kb)))),
            label=f"{self.label}.keys",
        )

    def _query_node(self, q: Q) -> F[Maybe[W]]:
        fn = self._fn
        label = f"{self.label}[{q}]"

        def combine(a: Maybe[A], b: Maybe[B]) -> Maybe[W]:
            try:
                return fn(a, b)
            except Exception as err:
                err.add_note(f"while combining {label}")
                raise

        return self._a.query(q).bind(
            lambda a: self._b.query(q).map(lambda b: combine(a, b), label=f"{label} rhs"),
            label=label,
        )


class MapNSeries[K: Key, V, W, Q = K](Series[K, W, Q]):
    """A view combining any number of same-typed series' answers pointwise.

    The n-ary counterpart to :class:`Map2Series`: sources share one key and
    value type, and ``fn`` receives every source's answer as a positional
    tuple, in source order, and returns the combined answer. Every source is
    asked *every* query, including where it has no coverage, so ``fn`` sees
    ``MISSING`` in any position and states the policy — sum a cohort with
    ``lambda answers: sum(or_else(a, 0.0) for a in answers)``, refuse partial
    coverage by testing for :class:`~orcaset.maybe.Missing` yourself. Keys are
    produced by one n-way ordered sweep over the sources' key runs.

    All sources must interpret ``Q`` the same way, as with
    :class:`Map2Series`. ``fn`` must also be total on the empty tuple: an
    empty source list is a valid series with no keys whose every answer is
    ``fn(())``, so a summing combine merges to zero and a strict one to
    ``MISSING``.

    Source nodes are gathered as a balanced tree, so bind depth is
    ``O(log n)``. The source sequence is copied at construction: node identity
    is object identity, so the merged graph must not change under a caller's
    later mutation.
    """

    __slots__ = ("_fn", "_sources")

    def __init__(
        self,
        sources: Sequence[Series[K, V, Q]],
        fn: Callable[[tuple[Maybe[V], ...]], Maybe[W]],
        *,
        label: str,
    ) -> None:
        super().__init__(label=label)
        self._sources: tuple[Series[K, V, Q], ...] = tuple(sources)
        self._fn = fn

    def _keys_node(self) -> Keys[K]:
        sources = self._sources
        label = f"{self.label}.keys"

        if not sources:
            return Delay(lambda: Replay[K](()), label=label)
        if len(sources) == 1:
            return sources[0].keys()

        def gather(lo: int, hi: int) -> F[tuple[Replay[K], ...]]:
            if hi - lo == 1:
                return sources[lo].keys().map(lambda keys: (keys,), label=f"{label} @{lo}")
            mid = (lo + hi) // 2
            left, right = gather(lo, mid), gather(mid, hi)
            return left.bind(
                lambda left_keys: right.map(
                    lambda right_keys: left_keys + right_keys,
                    label=f"{label} [{mid}:{hi}]",
                ),
                label=label if lo == 0 and hi == len(sources) else f"{label}[{lo}:{hi}]",
            )

        return gather(0, len(sources)).map(
            lambda key_runs: Replay(ordered_union(key_runs)),
            label=label,
        )

    def _query_node(self, q: Q) -> F[Maybe[W]]:
        fn = self._fn
        sources = self._sources
        label = f"{self.label}[{q}]"

        def combine(answers: tuple[Maybe[V], ...]) -> Maybe[W]:
            try:
                return fn(answers)
            except Exception as err:
                err.add_note(f"while combining {label}")
                raise

        if not sources:
            return Delay(lambda: combine(()), label=label)

        def gather(lo: int, hi: int) -> F[tuple[Maybe[V], ...]]:
            if hi - lo == 1:
                return sources[lo].query(q).map(lambda a: (a,), label=f"{label} @{lo}")
            mid = (lo + hi) // 2
            left, right = gather(lo, mid), gather(mid, hi)
            return left.bind(
                lambda la: right.map(lambda ra: la + ra, label=f"{label} [{mid}:{hi}]"),
                label=f"{label} [{lo}:{hi}]",
            )

        return gather(0, len(sources)).map(combine, label=label)


class _End:
    """Sentinel for an exhausted key iterator."""

    __slots__: tuple[str, ...] = ()


_END = _End()


def ordered_union[K: Key](runs: Iterable[Iterable[K]]) -> Iterator[K]:
    """Lazily sweep strictly increasing key runs into their ordered union.

    Equivalent heads across any number of runs collapse to one key. Laziness
    matters: a merged view over infinite series must still be enumerable up to
    a point.
    """
    iterators = tuple(iter(run) for run in runs)
    heads: list[K | _End] = [next(iterator, _END) for iterator in iterators]

    while True:
        first = next(
            (index for index, head in enumerate(heads) if not isinstance(head, _End)),
            None,
        )
        if first is None:
            return

        minimum = heads[first]
        assert not isinstance(minimum, _End)
        for head in heads[first + 1 :]:
            if not isinstance(head, _End) and head < minimum:
                minimum = head

        yield minimum
        for index, head in enumerate(heads):
            if not isinstance(head, _End) and not head < minimum and not minimum < head:
                heads[index] = next(iterators[index], _END)


# Resampling ----------------------------------------------------------------


def resample[K0: Key, V, W, K: Key, Q = K](
    source: Series[K0, V, K],
    keys: Callable[[], Iterable[K]],
    resolve: Callable[[K, Maybe[V]], W],
    select: Select[K, W, Q],
    reduce: Reduce[K, W],
    *,
    label: str,
) -> LeafSeries[K, W, Q]:
    """Re-key a series by tabulating its answers on a new grid.

    The new key type must be a valid query on ``source``: an annual period
    queries a monthly series and the source's own convention does the
    aggregation. Each new cell is ``source.query(key)`` passed through
    ``resolve``, which states what an unanswerable grid point means —
    ``lambda _, a: or_else(a, 0.0)`` to fill, ``lambda _, a: unwrap(a)`` to
    fail, ``lambda _, a: a`` to keep the ``Maybe`` (making the resampled
    value type ``Maybe[V]``).

    The result carries its own convention at the new granularity, so
    sub-grid queries answer from the new cells: clipping an annual cell
    prorates the annual total rather than re-reading the source. That
    divergence is what materializing means. Cells are the source's memoized
    query nodes, so the full source provenance stays reachable from every
    resampled cell.
    """

    def cells() -> Iterator[Cell[K, W]]:
        for key in keys():
            yield (
                key,
                source.query(key).map(
                    lambda answer, key=key: resolve(key, answer), label=f"{label}@{key}"
                ),
            )

    return LeafSeries.from_cells(cells, select, reduce, label=label)


def rekey[K0: Key, V, W, K: Key, Q = K](
    source: Series[K0, V, K],
    grid: Callable[[Iterable[K0]], Iterable[K]],
    resolve: Callable[[K, Maybe[V]], W],
    select: Select[K, W, Q],
    reduce: Reduce[K, W],
    *,
    label: str,
) -> LeafSeries[K, W, Q]:
    """Resample onto a grid derived from the source's own keys.

    ``grid`` maps the source key run to the new one — monthly periods to the
    years containing them, deduped and increasing. Unlike :func:`resample`
    the stream depends on ``source.keys()``, so the source's key sequence is
    materialized before any cell exists.
    """

    def cells(source_keys: Replay[K0]) -> Iterator[Cell[K, W]]:
        for key in grid(source_keys):
            yield (
                key,
                source.query(key).map(
                    lambda answer, key=key: resolve(key, answer), label=f"{label}@{key}"
                ),
            )

    stream: Stream[K, W] = source.keys().map(
        lambda source_keys: CellReplay(cells(source_keys)), label=f"{label} stream"
    )
    return LeafSeries(stream, select, reduce, label=label)
