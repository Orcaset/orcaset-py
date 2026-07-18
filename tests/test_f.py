# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

import pytest

from orcaset import Apply, Bind, Context, F, Pure


def test_deep_map_chain() -> None:
    value = F.pure(0)
    for _ in range(10_000):
        value = value.map(lambda x: x + 1)

    assert value.run(Context()) == 10_000


def test_deep_bind_chain() -> None:
    value: F[int] = Pure(0)
    for _ in range(10_000):
        value = value.bind(lambda x: Pure(x + 1))

    assert value.run(Context()) == 10_000


def test_deep_apply_chain() -> None:
    value: F[int] = Pure(0)
    for _ in range(10_000):
        value = Pure(lambda x: x + 1).apply(value)

    assert value.run(Context()) == 10_000


def test_cache_reuses_shared_subgraph() -> None:
    calls = 0

    def tick() -> int:
        nonlocal calls
        calls += 1
        return 1

    shared = F.delay(tick, label="shared")
    total = shared.bind(lambda a: shared.map(lambda b: a + b), label="total")

    ctx = Context()
    assert total.run(ctx) == 2
    assert calls == 1
    assert total.run(ctx) == 2
    assert calls == 1


def test_cycle_raises() -> None:
    cells: list[F[int]] = []

    def loop(_: int) -> F[int]:
        return cells[0]

    node: F[int] = Pure(0).bind(loop)
    cells.append(node)

    with pytest.raises(RuntimeError, match="cycle detected"):
        node.run(Context())


def test_edges_recorded_for_map_and_bind() -> None:
    src = Pure(1, label="src")
    mapped = src.map(lambda x: x + 1, label="mapped")
    bound = mapped.bind(lambda x: Pure(x * 2), label="bound")

    ctx = Context()
    assert bound.run(ctx) == 4

    edge_ids = {(p.id, c.id) for p, c in ctx.edges}
    assert (mapped.id, src.id) in edge_ids
    assert (bound.id, mapped.id) in edge_ids


def test_apply_matches_bind_map() -> None:
    ff = Pure(lambda x: x * 3)
    fa = Pure(7)

    via_apply = ff.apply(fa)
    via_bind = ff.bind(lambda f: fa.map(f))

    ctx = Context()
    assert via_apply.run(ctx) == 21
    assert via_bind.run(Context()) == 21
    assert isinstance(via_apply, Apply)
    assert isinstance(via_apply, F)

    edge_ids = {(p.id, c.id) for p, c in ctx.edges}
    assert (via_apply.id, ff.id) in edge_ids
    assert (via_apply.id, fa.id) in edge_ids


def test_apply_reuses_shared_argument() -> None:
    calls = 0

    def tick() -> int:
        nonlocal calls
        calls += 1
        return 7

    fa = F.delay(tick, label="fa")
    left = Pure(lambda x: x + 1).apply(fa, label="left")
    right = Pure(lambda x: x * 3).apply(fa, label="right")
    total = left.bind(lambda a: right.map(lambda b: a + b), label="total")

    ctx = Context()
    assert total.run(ctx) == 29
    assert calls == 1


def test_nested_run_from_delay_thunk() -> None:
    ctx = Context()
    inner = Pure(21, label="inner")

    outer = F.delay(lambda: inner.run(ctx) * 2, label="outer")
    assert outer.run(ctx) == 42
    assert inner.id in ctx.cache
