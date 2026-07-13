# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from datetime import date
from collections.abc import Iterable
from dateutil.relativedelta import relativedelta


class Period:
    def __init__(self, start: date, end: date):
        self.start = start
        self.end = end

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Period):
            return False
        return self.start == other.start and self.end == other.end

    def __hash__(self) -> int:
        return hash((self.start, self.end))

    def __repr__(self) -> str:
        return f"Period(start={self.start}, end={self.end})"

    @staticmethod
    def seq(start: date, freq: relativedelta, end: date | None = None) -> Iterable[Period]:
        while end is None or start <= end:
            yield Period(start, min(start + freq, end) if end is not None else start + freq)
            start += freq
