# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from typing import Iterator, cast, Any
from datetime import date

from .cell import Point, Span
from .period import Period
from .series import Series, SpanSeries, PointSeries


class _SpanCache:
    __slots__ = ("iterator", "spans", "_cursor_date", "_exhausted")

    def __init__(self, iterator: Iterator[Span], spans: dict[Period, Span | None]) -> None:
        self.iterator = iterator
        self.spans = spans
        # Date of last materialized span, or None if no spans have been materialized yet
        self._cursor_date: date | None = None
        self._exhausted = False

    def ensure_materialized_through(self, date: date) -> None:
        """Ensure that the cache is materialized through `date`."""
        while not self._exhausted and (self._cursor_date is None or date > self._cursor_date):
            try:
                next_span = next(self.iterator)
            except StopIteration:
                self._exhausted = True
                return
            self.spans[next_span.period] = next_span
            self._cursor_date = next_span.period.end


class Context:
    """`Context` manages all state for cell and value evaluation."""

    def __init__(self) -> None:
        self._values: dict[type[Series], Series] = {}
        self._span_cache: dict[int, _SpanCache] = {}
        self._point_cache: dict[int, dict[date, Point | None]] = {}
        self._formula_values: dict[int, Any] = {}

    def get[T: Series](self, series_type: type[T]) -> T:
        """
        Get a series instance of type `T`.

        If an instance of type `T` already exists, return it. Otherwise,
        create a new instance and store it.

        Member series are keyed by their type hashes which makes lookups
        invariant to the series type. In other words, getting `MySeries`
        will not match against any subclass of `MySeries`.
        """

        if series_type in self._values:
            return cast(T, self._values[series_type])
        instance = series_type(self)
        self._values[series_type] = instance
        return instance

    def get_or_create_span_cache(self, series: SpanSeries) -> _SpanCache:
        if series._id in self._span_cache:
            return self._span_cache[series._id]
        cache = _SpanCache(iter(series.spans()), {})
        self._span_cache[series._id] = cache
        return cache

    def get_or_create_point_cache(self, series: PointSeries) -> dict[date, Point | None]:
        if series._id in self._point_cache:
            return self._point_cache[series._id]
        self._point_cache[series._id] = {}
        return self._point_cache[series._id]
