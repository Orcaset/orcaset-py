# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from dateutil.relativedelta import relativedelta


class Period:
    """A span of time with a partial order over non-overlapping intervals.

    ``a < b`` iff ``a`` ends at or before ``b`` starts; ``a > b`` iff ``a``
    starts at or after ``b`` ends. Overlapping periods are incomparable
    (comparisons return ``NotImplemented``).

    The start date must be strictly before the end date. Raises a ValueError if not.
    """

    def __init__(self, start: date, end: date):
        if start >= end:
            raise ValueError(f"Period start {start} must be strictly before end {end}")
        self.start = start
        self.end = end

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Period):
            return NotImplemented
        return self.start == other.start and self.end == other.end

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Period):
            return NotImplemented
        if self.end <= other.start:
            return True
        if self.start >= other.end:
            return False
        if self == other:
            return False
        return NotImplemented

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, Period):
            return NotImplemented
        if self.start >= other.end:
            return True
        if self.end <= other.start:
            return False
        if self == other:
            return False
        return NotImplemented

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Period):
            return NotImplemented
        if self == other or self.end <= other.start:
            return True
        if self.start >= other.end:
            return False
        return NotImplemented

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, Period):
            return NotImplemented
        if self == other or self.start >= other.end:
            return True
        if self.end <= other.start:
            return False
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.start, self.end))

    def __repr__(self) -> str:
        return f"Period(start={self.start}, end={self.end})"

    def __str__(self) -> str:
        return f"{self.start}..{self.end}"

    def shift(self, delta: relativedelta) -> Period:
        """Translate both endpoints by ``delta`` (e.g. ``years=-1`` for the year-ago period)."""
        return Period(self.start + delta, self.end + delta)

    @staticmethod
    def seq(start: date, freq: relativedelta, end: date | None = None) -> Iterable[Period]:
        """Yield consecutive periods of ``freq`` from ``start``.

        Boundaries are computed from the origin (``start + i * freq``), not by
        accumulation, so month-end boundaries do not drift (e.g. quarterly
        periods from 12-31 end on 03-31, 06-30, 09-30, 12-31).
        """
        i = 0
        while True:
            period_start = start + freq * i
            if end is not None and period_start > end:
                return
            period_end = start + freq * (i + 1)
            yield Period(period_start, min(period_end, end) if end is not None else period_end)
            i += 1
