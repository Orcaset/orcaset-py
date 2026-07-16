# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from itertools import count

ids = count()


def next_id() -> int:
    return next(ids)
