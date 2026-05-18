# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

import itertools
from abc import ABC, abstractmethod
from datetime import date
from typing import TYPE_CHECKING, Callable, Iterable, cast, final

from .cell import Point, Span
from .period import Period
from .formula import Formula, Op

if TYPE_CHECKING:
    from .context import Context


class Series(ABC):
    """
    The base class for all series types. Series represent (part of) a line item in a financial statement.

    Series should not be instantiated directly. Instead, use `Context.get` to create a series instance.
    """

    _ids = itertools.count()

    @final
    def __init__(self, ctx: Context):
        self._id = next(Series._ids)
        self.ctx = ctx
        self.__post_init__()

    def __repr__(self) -> str:
        return f"Series(id={self._id})"

    def __post_init__(self) -> None:
        """Post-initialization hook."""
        pass


class PointSeries(Series):
    @classmethod
    def define[S: "PointSeries"](
        cls: type[S],
        fn: Callable[[S, date], Formula[float | None]],
        /,
    ) -> type[S]:
        return cast(
            type[S],
            type(
                fn.__name__,
                (cls,),
                {
                    "__module__": fn.__module__,
                    "__qualname__": fn.__qualname__,
                    "__doc__": fn.__doc__,
                    "point": fn,
                },
            ),
        )

    def query(self, dt: date) -> Formula[Point]:
        point_cache = self.ctx.get_or_create_point_cache(self)
        if dt in point_cache:
            return Formula.pure(point_cache[dt])

        point = self.point(dt)
        point_cache[dt] = Point(dt, point)
        return Formula.pure(point_cache[dt])

    @abstractmethod
    def point(self, dt: date) -> Formula[float | None]:
        raise NotImplementedError


class SpanQueryOp(Op[list[Span]]):
    def __init__(self, series: "SpanSeries", period: Period) -> None:
        self.series = series
        self.period = period

    def eval(self) -> list[Span]:
        span_cache = self.series.ctx.get_or_create_span_cache(self.series)

        # If the period is already materialized, return the span.
        if self.period in span_cache.spans:
            return [span_cache.spans[self.period]]

        span_cache.ensure_materialized_through(self.period.end)
        return [
            s
            for s in span_cache.spans.values()
            if s.period.end >= self.period.start and s.period.start <= self.period.end
        ]

    def __repr__(self) -> str:
        return f"SpanQueryOp(series={self.series!r}, period={self.period!r})"


class SpanSeries(Series):
    @classmethod
    def define[S: "SpanSeries"](
        cls: type[S],
        fn: Callable[[S], Iterable[Span]],
        /,
    ) -> type[S]:
        return cast(
            type[S],
            type(
                fn.__name__,
                (cls,),
                {
                    "__module__": fn.__module__,
                    "__qualname__": fn.__qualname__,
                    "__doc__": fn.__doc__,
                    "spans": fn,
                },
            ),
        )

    def query(self, period: Period) -> Formula[list[Span]]:
        return Formula(SpanQueryOp(self, period))

    @abstractmethod
    def spans(self) -> Iterable[Span]:
        raise NotImplementedError
