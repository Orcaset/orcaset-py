# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Hashable
from typing import Protocol

from orcaset.ids import next_id


class Fetch(Protocol):
    def __call__[DepK: Hashable, DepV](self, rule: Rule[DepK, DepV], key: DepK) -> DepV: ...


class Rule[K: Hashable, V](ABC):
    def __init__(self, name: str):
        self._name = name
        self._id = next_id()

    @property
    def id(self) -> int:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @abstractmethod
    def compute(self, fetch: Fetch, key: K) -> V: ...
