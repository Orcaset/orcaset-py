# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from abc import ABCMeta, abstractmethod
from collections.abc import Callable, Hashable, Mapping, Sequence
from datetime import date
from typing import TYPE_CHECKING, cast, overload

from ._value_ops import (
    ValueOp,
    add_scalar_values,
    div_scalar_values,
    div_values,
    mul_values,
    neg_values,
    rdiv_scalar_values,
    rsub_scalar_values,
    scale_values,
    sub_scalar_values,
    sub_values,
    sum_values,
)
from .cell import Point, Span
from .formula import Formula, Op
from .period import Period
from .series import Series
from .span import SpanSeries

if TYPE_CHECKING:
    from .context import Context


type PointFamilyResult[K: Hashable] = Mapping[K, Point]


class _PointSeriesMeta(ABCMeta):
    def __neg__(cls) -> type["PointSeries"]:
        return neg(cls)

    @overload
    def __add__(cls, other: type["PointSeries"], /) -> type["PointSeries"]: ...

    @overload
    def __add__(cls, other: int | float, /) -> type["PointSeries"]: ...

    def __add__(cls, other: object, /) -> object:
        if isinstance(other, _PointSeriesMeta):
            return sum([cls, other], name=f"Add{cls.__name__}{other.__name__}")
        if isinstance(other, int | float):
            return add_scalar(cls, other)
        return NotImplemented

    @overload
    def __radd__(cls, other: type["PointSeries"], /) -> type["PointSeries"]: ...

    @overload
    def __radd__(cls, other: int | float, /) -> type["PointSeries"]: ...

    def __radd__(cls, other: object, /) -> object:
        if isinstance(other, _PointSeriesMeta):
            return sum([other, cls], name=f"Add{other.__name__}{cls.__name__}")
        if isinstance(other, int | float):
            return add_scalar(cls, other)
        return NotImplemented

    @overload
    def __sub__(cls, other: type["PointSeries"], /) -> type["PointSeries"]: ...

    @overload
    def __sub__(cls, other: int | float, /) -> type["PointSeries"]: ...

    def __sub__(cls, other: object, /) -> object:
        if isinstance(other, _PointSeriesMeta):
            return sub(cls, other)
        if isinstance(other, int | float):
            return sub_scalar(cls, other)
        return NotImplemented

    @overload
    def __rsub__(cls, other: type["PointSeries"], /) -> type["PointSeries"]: ...

    @overload
    def __rsub__(cls, other: int | float, /) -> type["PointSeries"]: ...

    def __rsub__(cls, other: object, /) -> object:
        if isinstance(other, _PointSeriesMeta):
            return sub(other, cls)
        if isinstance(other, int | float):
            return rsub_scalar(other, cls)
        return NotImplemented

    @overload
    def __mul__(cls, other: type["PointSeries"], /) -> type["PointSeries"]: ...

    @overload
    def __mul__(cls, other: int | float, /) -> type["PointSeries"]: ...

    def __mul__(cls, other: object, /) -> object:
        if isinstance(other, _PointSeriesMeta):
            return mul([cls, other], name=f"Mul{cls.__name__}{other.__name__}")
        if isinstance(other, int | float):
            return scale(cls, other)
        return NotImplemented

    @overload
    def __rmul__(cls, other: type["PointSeries"], /) -> type["PointSeries"]: ...

    @overload
    def __rmul__(cls, other: int | float, /) -> type["PointSeries"]: ...

    def __rmul__(cls, other: object, /) -> object:
        if isinstance(other, _PointSeriesMeta):
            return mul([other, cls], name=f"Mul{other.__name__}{cls.__name__}")
        if isinstance(other, int | float):
            return scale(cls, other)
        return NotImplemented

    @overload
    def __truediv__(cls, other: type["PointSeries"], /) -> type["PointSeries"]: ...

    @overload
    def __truediv__(cls, other: int | float, /) -> type["PointSeries"]: ...

    def __truediv__(cls, other: object, /) -> object:
        if isinstance(other, _PointSeriesMeta):
            return div(cls, other)
        if isinstance(other, int | float):
            return div_scalar(cls, other)
        return NotImplemented

    @overload
    def __rtruediv__(cls, other: type["PointSeries"], /) -> type["PointSeries"]: ...

    @overload
    def __rtruediv__(cls, other: int | float, /) -> type["PointSeries"]: ...

    def __rtruediv__(cls, other: object, /) -> object:
        if isinstance(other, _PointSeriesMeta):
            return div(other, cls)
        if isinstance(other, int | float):
            return rdiv_scalar(other, cls)
        return NotImplemented


class PointSeries(Series, metaclass=_PointSeriesMeta):
    def query(self, dt: date) -> Formula[Point]:
        point_cache = self.ctx.get_or_create_point_cache(self)
        if dt in point_cache:
            return Formula.pure(point_cache[dt])

        point = self.point(dt)
        point_cache[dt] = Point(dt, point, self)
        return Formula.pure(point_cache[dt])

    def value(self, dt: date) -> Formula[float | None]:
        return self.query(dt).map(lambda point: point.eval(self.ctx))

    @abstractmethod
    def point(self, dt: date) -> Formula[float | None]:
        raise NotImplementedError


class PointSeriesFamily[K: Hashable](Series):
    def query(self, dt: date) -> Formula[PointFamilyResult[K]]:
        return Formula(PointFamilyQueryOp(self, dt))

    def key_label(self, key: K) -> str:
        return str(key)

    @abstractmethod
    def points(self, dt: date) -> PointFamilyResult[K]:
        raise NotImplementedError


class PointFamilyQueryOp[K: Hashable](Op[PointFamilyResult[K]]):
    def __init__(self, family: PointSeriesFamily[K], dt: date) -> None:
        self.family = family
        self.dt = dt

    def eval(self) -> PointFamilyResult[K]:
        result = dict(self.family.points(self.dt))
        for point in result.values():
            if point.source is None:
                point.source = self.family
        return result

    def __repr__(self) -> str:
        return f"PointFamilyQueryOp(family={self.family!r}, dt={self.dt!r})"


def define(
    fn: Callable[[PointSeries, date], Formula[float | None]],
    /,
) -> type[PointSeries]:
    return cast(
        type[PointSeries],
        type(
            fn.__name__,
            (PointSeries,),
            {
                "__module__": fn.__module__,
                "__qualname__": fn.__qualname__,
                "__doc__": fn.__doc__,
                "point": fn,
            },
        ),
    )


def accumulate(
    start: date,
    value: float | None,
    changes: type[SpanSeries],
    name: str = "AccumulatedPointSeries",
) -> type[PointSeries]:
    def point(self: PointSeries, dt: date) -> Formula[float | None]:
        if dt < start:
            return Formula.pure(None)
        if dt == start:
            return Formula.pure(value)

        spans = self.ctx.get(changes).query(Period(start, dt))

        def add_changes(spans: list[Span]) -> float | None:
            if value is None:
                return None

            total = 0.0
            for span in spans:
                span_value = span.fn.eval()
                if span_value is not None:
                    total += span_value
            return value + total

        return spans.map(add_changes)

    return type(name, (PointSeries,), {"point": point})


def neg(series: type[PointSeries], *, name: str | None = None) -> type[PointSeries]:
    return _operator(name or f"Neg{series.__name__}", [series], neg_values)


def scale(
    series: type[PointSeries],
    factor: float,
    *,
    name: str | None = None,
) -> type[PointSeries]:
    return _operator(name or f"Scale{series.__name__}", [series], scale_values(factor))


def add_scalar(
    series: type[PointSeries],
    value: int | float,
    *,
    name: str | None = None,
) -> type[PointSeries]:
    return _operator(name or f"Add{series.__name__}Scalar", [series], add_scalar_values(value))


def sum(
    series: Sequence[type[PointSeries]],
    *,
    name: str = "SumPointSeries",
) -> type[PointSeries]:
    return _operator(name, series, sum_values)


def sub(
    left: type[PointSeries],
    right: type[PointSeries],
    *,
    name: str | None = None,
) -> type[PointSeries]:
    return _operator(name or f"Sub{left.__name__}{right.__name__}", [left, right], sub_values)


def sub_scalar(
    series: type[PointSeries],
    value: int | float,
    *,
    name: str | None = None,
) -> type[PointSeries]:
    return _operator(name or f"Sub{series.__name__}Scalar", [series], sub_scalar_values(value))


def rsub_scalar(
    value: int | float,
    series: type[PointSeries],
    *,
    name: str | None = None,
) -> type[PointSeries]:
    return _operator(name or f"RSubScalar{series.__name__}", [series], rsub_scalar_values(value))


def mul(
    series: Sequence[type[PointSeries]],
    *,
    name: str = "MulPointSeries",
) -> type[PointSeries]:
    return _operator(name, series, mul_values)


def div(
    left: type[PointSeries],
    right: type[PointSeries],
    *,
    name: str | None = None,
) -> type[PointSeries]:
    return _operator(name or f"Div{left.__name__}{right.__name__}", [left, right], div_values)


def div_scalar(
    series: type[PointSeries],
    value: int | float,
    *,
    name: str | None = None,
) -> type[PointSeries]:
    return _operator(name or f"Div{series.__name__}Scalar", [series], div_scalar_values(value))


def rdiv_scalar(
    value: int | float,
    series: type[PointSeries],
    *,
    name: str | None = None,
) -> type[PointSeries]:
    return _operator(name or f"RDivScalar{series.__name__}", [series], rdiv_scalar_values(value))


def _operator(
    name: str,
    series_types: Sequence[type[PointSeries]],
    op: ValueOp,
) -> type[PointSeries]:
    def point(self: PointSeries, dt: date) -> Formula[float | None]:
        points: list[Point] = [
            self.ctx.get(series_type).query(dt).eval() for series_type in series_types
        ]
        return Formula(_PointTupleValueOp(self.ctx, points, op))

    return type(name, (PointSeries,), {"point": point})


class _PointTupleValueOp(Op[float | None]):
    def __init__(self, ctx: "Context", points: Sequence[Point], op: ValueOp) -> None:
        self.ctx = ctx
        self.points = points
        self.op = op

    def eval(self) -> float | None:
        return self.op([point.eval(self.ctx) for point in self.points])

    def __repr__(self) -> str:
        return f"PointTupleValueOp(points={self.points!r})"
