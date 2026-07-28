from __future__ import annotations

from collections.abc import Callable, Hashable, Iterable, Iterator
from datetime import date

from orcaset import Context, Period, Rule, Step, fetch


class _ReplayableIterator[T](Iterator[T]):
    def __init__(self, owner: Replayable[T]):
        self._owner = owner
        self._index = 0

    def __next__(self) -> T:
        if self._index < len(self._owner._buffer):
            item = self._owner._buffer[self._index]
        else:
            item = next(self._owner._source)
            self._owner._buffer.append(item)
        self._index += 1
        return item


class Replayable[T](Iterable[T]):
    """Buffered iterable that can be re-iterated without re-consuming the source.

    Items are pulled lazily from the source and appended to a shared buffer, so
    the source may be infinite. Each call to ``iter`` returns a new iterator
    that replays from the start of the buffer.
    """

    def __init__(self, iterable: Iterable[T]):
        self._source = iter(iterable)
        self._buffer: list[T] = []

    def __iter__(self) -> Iterator[T]:
        return _ReplayableIterator(self)


class ReplayableRule[T](Rule[None, Iterable[T]]):
    def __init__(self, iterable: Callable[[], Iterable[T]]):
        super().__init__("ReplayableRule")
        self.iterable = iterable

    def compute(self, key: None) -> Iterable[T]:
        return Replayable(self.iterable())


type Select[K: Hashable, V] = Callable[[Iterable[tuple[K, V]], K], list[tuple[K, V]]]
type Reduce[K: Hashable, V] = Callable[[Iterable[tuple[K, V]]], V]


class SeriesRule[K: Hashable, V](Rule[K, V]):
    def __init__(
        self, iterable: ReplayableRule[tuple[K, V]], select: Select[K, V], reduce: Reduce[K, V]
    ):
        super().__init__("SeriesRule")
        self.iterable = iterable
        self.select = select
        self.reduce = reduce

    def compute(self, key: K) -> Step[V]:
        series = yield from fetch(self.iterable, None)
        items = self.select(series, key)
        return self.reduce(items)


def periods_over[V](index: Iterable[tuple[Period, V]], period: Period) -> list[tuple[Period, V]]:
    return [item for item in index if period.end > item[0].start and period.start < item[0].end]


def sum_values(items: Iterable[tuple[Period, float]]) -> float:
    return sum(item[1] for item in items)


def revenue_generator() -> Iterator[tuple[Period, float]]:
    yield Period(date(2025, 12, 31), date(2026, 1, 31)), 100.0
    yield Period(date(2026, 1, 31), date(2026, 2, 28)), 200.0
    yield Period(date(2026, 2, 28), date(2026, 3, 31)), 300.0


revenue = SeriesRule(ReplayableRule(revenue_generator), periods_over, sum_values)


ctx = Context()
print(ctx.demand(revenue, Period(date(2026, 1, 31), date(2026, 3, 31))))
