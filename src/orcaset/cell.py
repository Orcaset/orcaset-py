# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

import itertools
from datetime import date
from typing import TYPE_CHECKING

from .formula import Formula
from .period import Period

if TYPE_CHECKING:
    from .context import Context


class Cell:
    _ids = itertools.count()
    fn: Formula[float | None]

    def __init__(self):
        self._id = next(Cell._ids)

    def id(self) -> int:
        return self._id

    def eval(self, ctx: "Context") -> float | None:
        return ctx.eval_cell(self)


class Span(Cell):
    def __init__(self, period: Period, fn: Formula[float | None]):
        super().__init__()
        self.period = period
        self.fn = fn

    def __repr__(self) -> str:
        return f"Span(period={self.period}, fn={self.fn!r})"


class Point(Cell):
    def __init__(self, dt: date, fn: Formula[float | None]):
        super().__init__()
        self.dt = dt
        self.fn = fn

    def __repr__(self) -> str:
        return f"Point(dt={self.dt}, fn={self.fn!r})"
