# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from collections.abc import Generator
from datetime import date
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


def period_union(left: Period, right: Period, /) -> tuple[Period, Period | None, Period | None]:
    """``KeyMerge`` for periods: re-tile the union at every source boundary.

    Returns the first piece of ``left ∪ right`` and what remains of each
    operand after it (``None`` when consumed). Ordered heads pass through
    unchanged, so gaps are never filled; overlapping heads are split.
    """
    if left < right:
        return left, None, right
    if right < left:
        return right, left, None
    if left == right:
        return left, None, None
    if left.start < right.start:
        return Period(left.start, right.start), Period(right.start, left.end), right
    if right.start < left.start:
        return Period(right.start, left.start), left, Period(left.start, right.end)
    end = min(left.end, right.end)
    return (
        Period(left.start, end),
        None if left.end == end else Period(end, left.end),
        None if right.end == end else Period(end, right.end),
    )


def date_union(left: date, right: date, /) -> tuple[date, date | None, date | None]:
    """``KeyMerge`` for dates: ascending merge, duplicates emitted once."""
    if left < right:
        return left, None, right
    if right < left:
        return right, left, None
    return left, None, None
