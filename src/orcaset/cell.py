# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

import itertools
from datetime import date

from .formula import Formula
from .period import Period


class Cell:
    _ids = itertools.count()

    def __init__(self):
        self._id = next(Cell._ids)


class Span(Cell):
    def __init__(self, period: Period, fn: Formula):
        super().__init__()
        self.period = period
        self.fn = fn

    def __repr__(self) -> str:
        return f"Span(period={self.period}, fn={self.fn!r})"


class Point(Cell):
    def __init__(self, dt: date, fn: Formula):
        super().__init__()
        self.dt = dt
        self.fn = fn

    def __repr__(self) -> str:
        return f"Point(dt={self.dt}, fn={self.fn!r})"
