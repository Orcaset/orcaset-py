# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

import builtins
from collections.abc import Callable, Sequence
from typing import cast

# Shared null-aware numeric reducers used by point and span series combinators.
type ValueOp = Callable[[Sequence[float | None]], float | None]


def none_if_any_none(values: Sequence[float | None]) -> list[float] | None:
    if any(value is None for value in values):
        return None
    return cast(list[float], list(values))


def neg_values(values: Sequence[float | None]) -> float | None:
    resolved = none_if_any_none(values)
    return None if resolved is None else -resolved[0]


def scale_values(factor: float) -> ValueOp:
    def op(values: Sequence[float | None]) -> float | None:
        resolved = none_if_any_none(values)
        return None if resolved is None else resolved[0] * factor

    return op


def sum_values(values: Sequence[float | None]) -> float | None:
    resolved = none_if_any_none(values)
    return None if resolved is None else builtins.sum(resolved)


def sub_values(values: Sequence[float | None]) -> float | None:
    resolved = none_if_any_none(values)
    return None if resolved is None else resolved[0] - resolved[1]


def mul_values(values: Sequence[float | None]) -> float | None:
    resolved = none_if_any_none(values)
    if resolved is None:
        return None
    product = 1.0
    for value in resolved:
        product *= value
    return product


def div_values(values: Sequence[float | None]) -> float | None:
    resolved = none_if_any_none(values)
    return None if resolved is None else resolved[0] / resolved[1]
