# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

import itertools
from abc import ABC
from typing import TYPE_CHECKING, ClassVar, final

if TYPE_CHECKING:
    from .context import Context


class Series(ABC):
    """
    The base class for all series types. Series represent (part of) a line item in a financial statement.

    Series should not be instantiated directly. Instead, use `Context.get` to create a series instance.
    """

    _ids = itertools.count()
    label: ClassVar[str | None] = None

    @final
    def __init__(self, ctx: Context):
        self._id = next(Series._ids)
        self.ctx = ctx
        self.__post_init__()

    @property
    def id(self) -> int:
        return self._id

    def __repr__(self) -> str:
        return f"Series(id={self.id})"

    @classmethod
    def display_name(cls) -> str:
        return cls.label or cls.__name__

    def __post_init__(self) -> None:
        """Post-initialization hook."""
        pass
