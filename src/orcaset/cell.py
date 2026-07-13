# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from dataclasses import dataclass
from datetime import date as Date

from .f import F
from .period import Period


@dataclass(frozen=True, slots=True)
class Point[T]:
    date: Date
    value: F[T]


@dataclass(frozen=True, slots=True)
class Span[T]:
    period: Period
    value: F[T]
