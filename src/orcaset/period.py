# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from collections import namedtuple
from datetime import date
from typing import Generator

from dateutil.relativedelta import relativedelta


class InvalidPeriodError(Exception):
    """Error raised when trying to create a `Period` with `start` on or after `end`."""

    pass


_Period = namedtuple("_Period", ["start", "end"])


class Period(_Period):
    __slots__ = ()

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
    def seq(
        cls, start: date, freq: relativedelta, end: date | None
    ) -> Generator[Period, None, None]:
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
