# `orcaset` API summary

## query

```py
type DayCount = Callable[[date, date], float]  # Length of an ordered date pair (year fraction, days, …)

def exact[K: Key, V](q: K, cells: Iterable[tuple[K, Rule[V]]]) -> Step[Maybe[V]]:  # Point lookup, or Na
def exact_or[K: Key, V](default: V) -> QueryFn[K, K, V, V]:  # Like exact, but default on miss
def last[K: Key, V](q: K, cells: Iterable[tuple[K, Rule[V]]]) -> Step[Maybe[V]]:  # Latest cell at or before q, or Na
def accrual(yf: DayCount) -> QueryFn[Period, Period, float, Maybe[float]]:  # Weight overlapping cells by yf
def accrual_or(yf: DayCount, default: float) -> QueryFn[Period, Period, float, float]:  # Like accrual, but default on miss
def covered(q: Period, cells: Iterable[tuple[Period, Rule[float]]]) -> Step[Maybe[float]]:  # Sum cells that exactly tile q; Na on gap or partial overlap
```

## yf

```py
class YF:
    act360 = Callable[[date, date], float]
    thirty360 = Callable[[date, date], float]
    cmonthly = Callable[[date, date], float]
    na = Callable[[date, date], float]
```

## context

```py
class Context:
    def __init__(self, *, tol: float = 1e-9, max_iter: int = 1000) -> None:
    def get_at[K: Hashable, V](self, rule: KeyedRule[K, V], key: K) -> V:
    def get[V](self, rule: Rule[V]) -> V:
    def dependencies[K: Hashable, V](self, rule: KeyedRule[K, V], key: K) -> DepNode:
    def rule_dependencies[V](self, rule: Rule[V]) -> DepNode:

class CycleError(RuntimeError):  # Demand cycle with no seed/distance iterate policy
    path: tuple[tuple[int, Hashable], ...]

class ConvergenceError(RuntimeError):  # Cyclic demand did not settle within max_iter
    cell: tuple[int, Hashable]
    iterations: int
    residual: float
    tol: float
    values: tuple[Any, ...]  # Seed then each iterate
    residuals: tuple[float, ...]  # distance(values[i], values[i + 1])

class DepNode:
    name: str
    key: Hashable
    value: Any
    deps: tuple[DepNode, ...]
    def format(self, *, indent: str = "  ") -> str:
```

## period

```py
class Period(_Period):
    def __new__(cls, start: date, end: date):
    def from_end(self, offset: relativedelta) -> Period:  # New Period with dates end and end + offset
    def from_start(self, offset: relativedelta) -> Period:  # New Period with dates start and start + offset
    def shift(self, offset: relativedelta) -> Period:  # New Period with (p.start + offset, p.end + offset)
    def seq(cls, start: date, freq: relativedelta, end: date | None = None) -> Generator[Period]:  # Sequence of increasing, contiguous Periods
    def list(cls, start: date, freq: relativedelta, end: date) -> list[Period]:  # List of increasing, contiguous Periods

def period_union(domains: tuple[Iterable[Period], ...]) -> Iterator[Period]:  # Generator yielding ordered Periods with bounds at the union of all input Period bounds
def date_union(domains: tuple[Iterable[date], ...]) -> Iterator[date]:  # Generator yielding ordered, deduplicated date union from all inputs
```

## period_series

```py
class PeriodSeriesBase[W](BaseSeries[Period, Period, W], ABC):
    """Period-keyed series surface: ``map`` / ``map2`` / Na-aware ``+ - * /``."""
    def map[V](self, name: str, fn: Callable[[W], V]) -> PeriodMapSeries[W, V]:
        """Map over a PeriodSeriesBase converting value W to V."""

    def map2[W2, V](
        self,
        name: str,
        other: BaseSeries[Period, Period, W2],
        fn: Callable[[W, W2], V],
        *,
        merge_keys: Callable[[tuple[Iterable[Period], ...]], Iterable[Period]] | None = None,
    ) -> PeriodMap2Series[W, W2, V]:
        """Combine with any ``Period``-keyed series; domain defaults to ``period_union``."""
    
    def extend_with(
        self,
        name: str,
        continuation: Callable[[Period], PeriodSeriesBase[W]],
        combine: Callable[[W, W], W],
    ) -> PeriodExtendSeries[W]:
        """Answer from ``self`` until its domain is exhausted, then from ``continuation``.

        ``continuation`` receives the last base ``Period``. ``combine`` folds the
        two answers when a query spans that last ``end``.
        """
    def named(self, name: str) -> PeriodSeriesBase[W]:
        """Identity-mapped series with a new display name."""


class PeriodSeries[W](PeriodSeriesBase[W]):
    """Cell-backed series with ``Q = K = Period`` and ``period_union`` merges.

    Supports Na-propagating arithmetic via ``PeriodSeriesBase``. Derived series
    (``map``, ``map2``, operators) are ``PeriodSeriesBase``, not cell-backed grids.
    """

    def __init__[V](
        self,
        name: str,
        cells: CellsFn[Period, V],
        query: QueryFn[Period, Period, V, W],
    ):

    @classmethod
    def define[V, W2](
        cls,
        name: str,
        query: QueryFn[Period, Period, V, W2],
    ) -> Callable[[CellsFn[Period, V]], PeriodSeries[W2]]:
        """Decorator: build a ``PeriodSeries`` from a cells factory."""

class PeriodMapSeries[W, V](PeriodSeriesBase[V]):
    """Map resolved query answers while preserving a period-keyed surface.

    ``keys()`` aliases the source domain. ``fn`` receives the source's resolved
    answer at each query, including any miss sentinel returned by its query.
    """

class PeriodMap2Series[W1, W2, V](PeriodSeriesBase[V]):
    """Combine two period-keyed series' resolved answers at the same query.

    ``merge_keys`` constructs only the advertised domain; it does not affect
    query computation. The default ``period_union`` may advertise split
    fragments that a source's own query answers with ``Na``.
    """

class PeriodExtendSeries[W](PeriodSeriesBase[W]):
    """Answer from ``base`` until it is exhausted, then from a continuation series.

    ``continuation`` receives the last base ``Period``. Queries that end inside
    the base never materialize it. Queries that cross the last ``end`` are split
    there; each side is answered with that source's own query, then ``combine``.
    The base domain must be finite.
    """

    @classmethod
    def define[W2](
        cls,
        name: str,
        base: PeriodSeriesBase[W2],
        combine: Callable[[W2, W2], W2],
    ) -> Callable[[Callable[[Period], PeriodSeriesBase[W2]]], PeriodExtendSeries[W2]]:
        """Decorator: build a ``PeriodExtendSeries`` from a continuation factory."""
```

## date_series

```py
class DateSeriesBase[W](BaseSeries[date, date, W], ABC):
    """Date-keyed series surface: ``map`` / ``map2`` / Na-aware ``+ - * /``."""
    def map[V](self, name: str, fn: Callable[[W], V]) -> DateMapSeries[W, V]:
        """Map over a DateSeriesBase converting value W to V."""

    def map2[W2, V](
        self,
        name: str,
        other: BaseSeries[date, date, W2],
        fn: Callable[[W, W2], V],
        *,
        merge_keys: Callable[[tuple[Iterable[date], ...]], Iterable[date]] | None = None,
    ) -> DateMap2Series[W, W2, V]:
        """Combine with any ``date``-keyed series; domain defaults to ``date_union``."""

    def extend_with(
        self,
        name: str,
        continuation: Callable[[date], DateSeriesBase[W]],
    ) -> DateExtendSeries[W]:
        """Answer from ``self`` until ``continuation``'s domain begins.

        ``continuation`` receives the last base ``date`` and owns dates at or
        after its own first key. Point queries are not split: ``q`` is answered
        by the base while it is before the first continuation key (so an as-of
        base query carries forward across the seam), otherwise by the
        continuation.
        """
    def named(self, name: str) -> DateSeriesBase[W]:
        """Identity-mapped series with a new display name."""


class DateSeries[W](DateSeriesBase[W]):
    """Cell-backed series with ``Q = K = date`` and ``date_union`` merges.

    Supports Na-propagating arithmetic via ``DateSeriesBase``. Derived series
    (``map``, ``map2``, operators) are ``DateSeriesBase``, not cell-backed grids.
    """

    def __init__[V](
        self,
        name: str,
        cells: CellsFn[date, V],
        query: QueryFn[date, date, V, W],
    ):

    @classmethod
    def define[V, W2](
        cls,
        name: str,
        query: QueryFn[date, date, V, W2],
    ) -> Callable[[CellsFn[date, V]], DateSeries[W2]]:
        """Decorator: build a ``DateSeries`` from a cells factory."""

class DateMapSeries[W, V](DateSeriesBase[V]):
    """Map resolved query answers while preserving a date-keyed surface.

    ``keys()`` aliases the source domain. ``fn`` receives the source's resolved
    answer at each query, including any miss sentinel returned by its query.
    """

class DateMap2Series[W1, W2, V](DateSeriesBase[V]):
    """Combine two date-keyed series' resolved answers at the same query.

    ``merge_keys`` constructs only the advertised domain; it does not affect
    query computation. It defaults to the unique sorted ``date_union``.
    """

class DateExtendSeries[W](DateSeriesBase[W]):
    """Answer from ``base`` until the continuation's own domain begins.

    ``continuation`` receives the last base ``date`` and owns queries at or
    after its first key. Point queries are dispatched wholly to one side:
    dates before the first continuation key — including the gap after the
    last base date — use the base, so an as-of (``last``) base query carries
    forward across the seam; later dates use the continuation. Queries at or
    before the last base date never materialize the continuation. The base
    domain must be finite.
    """

    @classmethod
    def define[W2](
        cls,
        name: str,
        base: DateSeriesBase[W2],
    ) -> Callable[[Callable[[date], DateSeriesBase[W2]]], DateExtendSeries[W2]]:
        """Decorator: build a ``DateExtendSeries`` from a continuation factory."""
```

## series

```py
class Key(Hashable, Protocol):
    """Series key: hashable (cell identity) and comparable (lazy scans).

    ``a < b`` means "a is entirely before b". Overlapping keys (e.g. overlapping
    ``Period``s) may be mutually incomparable.
    """
    def __lt__(self, other: Self, /) -> bool: ...

type CellFactory[V] = Callable[[], Step[V] | V]
type CellStream[K: Key, V] = Generator[
    Demand[Any] | tuple[K, V | CellFactory[V]],
    Any,
    Iterable[tuple[K, V | CellFactory[V]]] | None,
]
type CellsFn[K: Key, V] = Callable[
    [],
    CellStream[K, V] | Iterable[tuple[K, V | CellFactory[V]]],
]
type QueryFn[Q, K: Key, V, W] = Callable[
    [Q, Iterable[tuple[K, Rule[V]]]],
    Step[W] | W,
]


class Replayable[T](Iterable[T]):
    """Buffered iterable that can be re-iterated without re-consuming the source."""
    def __init__(self, iterable: Iterable[T]) -> None:


class BaseSeries[Q: Hashable, K: Key, W](KeyedRule[Q, W], ABC):
    """A demandable rule with an explicit time domain.

    Values are only reachable through ``compute``, so every answer is
    dependency-tracked. Prefer ``PeriodSeries`` / ``DateSeries`` when ``Q`` and
    ``K`` are ``Period`` or ``date``.
    """
    def keys(self) -> Rule[Iterable[K]]:  # Demandable ascending domain (strictly ascending, possibly infinite)
    def map[V](self, name: str, fn: Callable[[W], V]) -> BaseSeries[Q, K, V]:
    def map2[W2, V](
        self,
        name: str,
        other: BaseSeries[Q, K, W2],
        fn: Callable[[W, W2], V],
        *,
        merge_keys: Callable[[tuple[Iterable[K], ...]], Iterable[K]],
    ) -> BaseSeries[Q, K, V]:


class Series[Q: Hashable, K: Key, V, W](BaseSeries[Q, K, W]):
    """Series backed by a lazy stream of ``(K, Rule[V])`` cells."""
    def __init__(
        self,
        name: str,
        cells: CellsFn[K, V],
        query: QueryFn[Q, K, V, W],
    ):

    @classmethod
    def define[Q2: Hashable, K2: Key, V2, W2](
        cls,
        name: str,
        query: QueryFn[Q2, K2, V2, W2],
    ) -> Callable[[CellsFn[K2, V2]], Series[Q2, K2, V2, W2]]:
        """Decorator: build a ``Series`` from a cells factory."""

class MapSeries[Q: Hashable, K: Key, W, V](BaseSeries[Q, K, V]):
    """Every answer is ``fn(source answered at q)``. ``keys()`` aliases the source."""

class Map2Series[Q: Hashable, K: Key, W1, W2, V](BaseSeries[Q, K, V]):
    """Combine two series at the same query; left and right answer types may differ.

    ``merge_keys`` only constructs the public domain; it is not used when answering a query.
    """

class MapNSeries[Q: Hashable, K: Key, W, V](BaseSeries[Q, K, V]):
    """Combine N source answers at the same query via ``fn(tuple[W, ...])``.

    An empty ``sources`` tuple is allowed: ``compute`` answers ``fn(())``.
    """

class MapItemsSeries[Q: Hashable, K: Key, V, W, A](BaseSeries[Q, K, A]):
    """Map each source key via ``fn(k, source)``, then query the derived stream.

    ``source`` must be ``BaseSeries[K, K, W]`` so domain keys are valid point queries.
    ``keys()`` aliases ``source.keys()``.
    """
    def __init__(
        self,
        name: str,
        source: BaseSeries[K, K, W],
        fn: Callable[[K, BaseSeries[K, K, W]], Step[V] | V],
        query: QueryFn[Q, K, V, A],
    ):
```

## rule

```py
type Step[V] = Generator[Demand[Any], Any, V]


class Rule[V](ABC):
    """A single memoized computation (no key)."""
    @property
    def id(self) -> int:
    @property
    def name(self) -> str:
    def compute(self) -> Step[V] | V:

class KeyedRule[K: Hashable, V](ABC):
    """A keyed family of memoized computations."""
    @property
    def id(self) -> int:
    @property
    def name(self) -> str:
    def compute(self, key: K, /) -> Step[V] | V:

class Demand[V]:
    """A request for another computation's value, yielded from ``compute``.

    Prefer ``get`` / ``get_at`` over yielding ``Demand`` directly.
    """
    target: KeyedRule[Any, V] | Rule[V]
    key: Hashable
    iterate: Iterate[V] | None

class Iterate[V]:
    """Fixed-point policy for a cyclic ``get`` / ``get_at``."""
    seed: V
    distance: Callable[[V, V], float]
    tol: float | None = None
    max_iter: int | None = None

def get_at[K: Hashable, V](
    rule: KeyedRule[K, V],
    key: K,
    *,
    seed: V = ...,
    distance: Callable[[V, V], float] = ...,
    tol: float | None = None,
    max_iter: int | None = None,
) -> Step[V]:
    """Request ``rule`` at ``key`` from within ``compute``. Always ``yield from``.

    Pass ``seed`` and ``distance`` together to solve a demand cycle.
    """

def get[V](
    rule: Rule[V],
    *,
    seed: V = ...,
    distance: Callable[[V, V], float] = ...,
    tol: float | None = None,
    max_iter: int | None = None,
) -> Step[V]:
    """Request an unkeyed ``Rule`` from within ``compute``. Always ``yield from``."""

def abs_distance(a: float, b: float) -> float:
def maybe_abs_distance(a: Maybe[float], b: Maybe[float]) -> float:  # Na vs non-Na is infinite
```

## maybe

```py
Na: _NaType  # Singleton miss sentinel; test with isna(value) or value is Na
type Maybe[V] = V | _NaType

def isna[V](value: Maybe[V]) -> TypeIs[_NaType]:
def map_some[A, B](fn: Callable[[A], B]) -> Callable[[Maybe[A]], Maybe[B]]:  # Na stays Na
def map2_some[A, B, C](fn: Callable[[A, B], C]) -> Callable[[Maybe[A], Maybe[B]], Maybe[C]]:  # Na if either side is Na
def combine_values[V](values: tuple[Maybe[V], ...], combine: Callable[[V, V], V]) -> Maybe[V]:  # Fold nonempty values; Na if empty or any Na
def add_values(values: tuple[Maybe[float], ...]) -> Maybe[float]:  # Sum floats, propagating Na
```

## stmt

```py
class PeriodValue:
    period: Period
    value: float | None

class DateValue:
    date: date
    value: float | None

class LineRow:
    name: str
    series: BaseSeries[Any, Any, Any]
    values: tuple[PeriodValue | DateValue, ...]

class TotalRow:
    name: str
    series: BaseSeries[Any, Any, Any]
    values: tuple[PeriodValue | DateValue, ...]
    children: tuple[StmtRow, ...]

class GroupRow:
    children: tuple[StmtRow, ...]

type StmtRow = LineRow | TotalRow | GroupRow
type StmtItem = BaseSeries[Any, Any, Any] | Total | Group

class StatementResult:
    rows: tuple[StmtRow, ...]
    periods: tuple[Period, ...]
    dates: tuple[date, ...]

class Total:
    series: BaseSeries[Any, Any, Any]
    items: tuple[StmtItem, ...]
    def __init__(self, series: BaseSeries[Any, Any, Any], items: Sequence[StmtItem]) -> None:

class Group:
    items: tuple[StmtItem, ...]
    def __init__(self, items: Sequence[StmtItem]) -> None:

class Stmt:
    def __init__(self, *items: StmtItem) -> None:
    def values(self, ctx: Context, periods: Sequence[Period]) -> StatementResult:  # Alias of values_for_periods
    def values_for_periods(self, ctx: Context, periods: Sequence[Period]) -> StatementResult:
        """Period series answer at each period; date series at period boundaries. Na becomes None."""
    def values_for_dates(self, ctx: Context, dates: Sequence[date]) -> StatementResult:
        """Date series answer at each date; period series contribute None."""
```

## formatters

```py
type ValueFormatter = Callable[[float | None], str]
type DateFormatter = Callable[[date], str]

def fixed_width_table(
    result: StatementResult,
    *,
    date_formatter: DateFormatter | None = None,
    value_formatter: ValueFormatter | None = None,
    indent: int = 2,
    padding: int = 2,
) -> str:

def csv_table(
    result: StatementResult,
    *,
    date_formatter: DateFormatter | None = None,
    value_formatter: ValueFormatter | None = None,
) -> str:

def markdown_table(
    result: StatementResult,
    *,
    date_formatter: DateFormatter | None = None,
    value_formatter: ValueFormatter | None = None,
    indent: int = 2,
) -> str:
```

Tables require a result with periods. Date-keyed values align to the first period start or to period ends.