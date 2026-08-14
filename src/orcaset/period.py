# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from collections.abc import Generator, Iterable, Iterator
from datetime import date
from heapq import merge
from typing import NamedTuple

from dateutil.relativedelta import relativedelta


class InvalidPeriodError(Exception):
    """Error raised when trying to create a `Period` with `start` on or after `end`."""


class _Period(NamedTuple):
    start: date
    end: date


class Period(_Period):
    """A period between two dates, `start` strictly before `end`.

    Ordering is "entirely before": `a < b` iff `a.end <= b.start`, so adjacent
    periods are ordered. This is a partial order — overlapping periods are
    mutually incomparable — so avoid `sorted()`/`min()`/`max()` over possibly
    overlapping periods; their results depend on input order.
    """

    def __new__(cls, start: date, end: date):
        if start >= end:
            raise InvalidPeriodError(
                "Invalid Period constructor args: "
                f"start date ({start.isoformat()}) must be strictly before "
                f"end date ({end.isoformat()})"
            )
        return super().__new__(cls, start, end)

    def __hash__(self) -> int:
        return hash((self.start, self.end))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Period):
            return NotImplemented
        return self.start == other.start and self.end == other.end

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Period):
            return NotImplemented
        return self.end <= other.start

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Period):
            return NotImplemented
        return self == other or self < other

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, Period):
            return NotImplemented
        return other < self

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, Period):
            return NotImplemented
        return self == other or other < self

    def __repr__(self) -> str:
        return f"Period({self.start.isoformat()}, {self.end.isoformat()})"

    def from_end(self, offset: relativedelta) -> Period:
        """New period with dates `end` and `end + offset`."""
        a, b = self.end, self.end + offset
        return Period(min(a, b), max(a, b))

    def from_start(self, offset: relativedelta) -> Period:
        """New period with dates `start` and `start + offset`."""
        a, b = self.start, self.start + offset
        return Period(min(a, b), max(a, b))

    def shift(self, offset: relativedelta) -> Period:
        """New period by shifting both start and end dates by `offset`."""
        return Period(self.start + offset, self.end + offset)

    @classmethod
    def seq(cls, start: date, freq: relativedelta, end: date | None = None) -> Generator[Period]:
        """
        Create a generator of periods with duration `freq`. Infinite if `end` is `None`.

        `freq` must monotonically advance the period in chronological order. Preserves month-end dates
        by multiplying `freq * period_count`.
        """
        i = 0
        end = end or date.max
        period = Period(start, min(start + freq, end))

        while period.start < end:
            yield period
            if period.end == end:
                break
            i += 1
            period = Period(start + (freq * i), min(start + (freq * (i + 1)), end))

    @classmethod
    def list(cls, start: date, freq: relativedelta, end: date) -> list[Period]:
        """
        Create a list of periods with duration `freq` ending at `end`.

        `freq` must monotonically advance the period in chronological order. Preserves month-end dates
        by multiplying `freq * period_count`.
        """
        return list(Period.seq(start, freq, end))


def period_union(domains: tuple[Iterable[Period], ...]) -> Iterator[Period]:
    """Lazily split the union of period domains at every source boundary.

    Each input must contain disjoint periods in strictly ascending order. Gaps
    not covered by any source are omitted.
    """
    iterators = tuple(iter(domain) for domain in domains)
    periods = [next(iterator, None) for iterator in iterators]
    starts = [period.start for period in periods if period is not None]
    if not starts:
        return
    boundary = min(starts)

    while any(period is not None for period in periods):
        candidates = [
            period.end if period.start <= boundary else period.start
            for period in periods
            if period is not None
        ]
        next_boundary = min(candidates)
        if any(period is not None and period.start <= boundary < period.end for period in periods):
            yield Period(boundary, next_boundary)
        boundary = next_boundary

        for index, period in enumerate(periods):
            if period is not None and period.end == boundary:
                periods[index] = next(iterators[index], None)


def date_union(domains: tuple[Iterable[date], ...]) -> Iterator[date]:
    """Lazily merge ascending date domains into a unique sorted spine.

    Each input must be strictly ascending. Duplicate dates within or across
    sources are emitted once.
    """
    prev: date | None = None
    for dt in merge(*domains):
        if dt != prev:
            yield dt
            prev = dt
