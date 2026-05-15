# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from typing import Protocol, Callable


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

    def __repr__(self) -> str:
        return f"Formula(op={self.op!r})"
