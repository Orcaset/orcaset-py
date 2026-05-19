# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from typing import Protocol, Callable, cast


type FormulaOperand[N: int | float | None] = Formula[N] | N


class Op[T](Protocol):
    def eval(self) -> T: ...


class ConstOp[T](Op[T]):
    def __init__(self, value: T) -> None:
        self.value = value

    def eval(self) -> T:
        return self.value

    def __repr__(self) -> str:
        return f"ConstOp(v={self.value!r})"


class MapOp[T, U](Op[U]):
    def __init__(self, source: Op[T], fn: Callable[[T], U]) -> None:
        self.source = source
        self.fn = fn

    def eval(self) -> U:
        return self.fn(self.source.eval())

    def __repr__(self) -> str:
        return f"MapOp(source={self.source!r}, fn={self.fn!r})"


class ApplyOp[T, U](Op[U]):
    def __init__(self, fn_op: Op[Callable[[T], U]], arg_op: Op[T]) -> None:
        self.fn_op = fn_op
        self.arg_op = arg_op

    def eval(self) -> U:
        return self.fn_op.eval()(self.arg_op.eval())

    def __repr__(self) -> str:
        return f"ApplyOp(fn_op={self.fn_op!r}, arg_op={self.arg_op!r})"


class Formula[T]:
    def __init__(self, op: Op[T]) -> None:
        self.op = op

    def eval(self) -> T:
        return self.op.eval()

    @staticmethod
    def pure(value: T) -> Formula[T]:
        return Formula(ConstOp(value))

    def map[U](self, fn: Callable[[T], U]) -> Formula[U]:
        return Formula(MapOp(self.op, fn))

    def apply[U, V](self: Formula[Callable[[U], V]], arg: Formula[U]) -> Formula[V]:
        return Formula(ApplyOp(self.op, arg.op))

    def map2[U, V](self, other: Formula[U], fn: Callable[[T, U], V]) -> Formula[V]:
        def curried(x: T, /) -> Callable[[U], V]:
            return lambda y: fn(x, y)

        return Formula.pure(curried).apply(self).apply(other)

    def __neg__[N: int | float | None](self: Formula[N]) -> Formula[int | float | None]:
        return _unary_formula(self, lambda x: -x)

    def __add__[L: int | float | None, R: int | float | None](
        self: Formula[L], other: FormulaOperand[R]
    ) -> Formula[int | float | None]:
        return _binary_formula(self, other, lambda x, y: x + y)

    def __radd__[N: int | float | None](
        self: Formula[N], other: int | float | None
    ) -> Formula[int | float | None]:
        return _binary_formula(other, self, lambda x, y: x + y)

    def __sub__[L: int | float | None, R: int | float | None](
        self: Formula[L], other: FormulaOperand[R]
    ) -> Formula[int | float | None]:
        return _binary_formula(self, other, lambda x, y: x - y)

    def __rsub__[N: int | float | None](
        self: Formula[N], other: int | float | None
    ) -> Formula[int | float | None]:
        return _binary_formula(other, self, lambda x, y: x - y)

    def __mul__[L: int | float | None, R: int | float | None](
        self: Formula[L], other: FormulaOperand[R]
    ) -> Formula[int | float | None]:
        return _binary_formula(self, other, lambda x, y: x * y)

    def __rmul__[N: int | float | None](
        self: Formula[N], other: int | float | None
    ) -> Formula[int | float | None]:
        return _binary_formula(other, self, lambda x, y: x * y)

    def __truediv__[L: int | float | None, R: int | float | None](
        self: Formula[L], other: FormulaOperand[R]
    ) -> Formula[int | float | None]:
        return _binary_formula(self, other, lambda x, y: x / y)

    def __rtruediv__[N: int | float | None](
        self: Formula[N], other: int | float | None
    ) -> Formula[int | float | None]:
        return _binary_formula(other, self, lambda x, y: x / y)

    def __floordiv__[L: int | float | None, R: int | float | None](
        self: Formula[L], other: FormulaOperand[R]
    ) -> Formula[int | float | None]:
        return _binary_formula(self, other, lambda x, y: x // y)

    def __rfloordiv__[N: int | float | None](
        self: Formula[N], other: int | float | None
    ) -> Formula[int | float | None]:
        return _binary_formula(other, self, lambda x, y: x // y)

    def __repr__(self) -> str:
        return f"Formula(op={self.op!r})"


def _unary_formula[N: int | float | None](
    formula: Formula[N], fn: Callable[[int | float], int | float]
) -> Formula[int | float | None]:
    return formula.map(lambda value: None if value is None else fn(cast(int | float, value)))


def _binary_formula[L: int | float | None, R: int | float | None](
    left: FormulaOperand[L],
    right: FormulaOperand[R],
    fn: Callable[[int | float, int | float], int | float],
) -> Formula[int | float | None]:
    left_formula = _as_formula(left)
    right_formula = _as_formula(right)
    return left_formula.map2(
        right_formula,
        lambda x, y: None
        if x is None or y is None
        else fn(cast(int | float, x), cast(int | float, y)),
    )


def _as_formula[N: int | float | None](value: FormulaOperand[N]) -> Formula[N]:
    if isinstance(value, Formula):
        return value
    if value is None or isinstance(value, int | float):
        return Formula.pure(value)
    raise TypeError(f"Unsupported Formula operand: {type(value).__name__}")
