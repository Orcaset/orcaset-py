"""Accepted and rejected argument shapes for ``Context.depends_on`` / ``path_to``."""

from datetime import date
from typing import assert_type

from orcaset import YF, Cell, Context, DepNode, Period, Series, accrue, ops

JAN = Period(date(2026, 1, 1), date(2026, 2, 1))
revenue = Series.of("Revenue", accrue(YF.cmonthly), [(JAN, 100.0)])
costs = ops.scale("Costs", revenue, -0.5)
total = Cell("total", lambda: 1.0)
ctx = Context()

assert_type(ctx.depends_on((costs, JAN), (revenue, JAN)), bool)
assert_type(ctx.depends_on(total, (revenue, JAN)), bool)
assert_type(ctx.depends_on((costs, JAN), total), bool)
assert_type(ctx.path_to((costs, JAN), (revenue, JAN)), tuple[DepNode, ...] | None)
assert_type(ctx.path_to(total, total, structural=True), tuple[DepNode, ...] | None)

ctx.depends_on((costs, "jan"), (revenue, JAN))  # pyrefly: ignore[bad-argument-type]
ctx.depends_on((costs, JAN), (revenue, date(2026, 1, 1)))  # pyrefly: ignore[bad-argument-type]
ctx.depends_on(costs, (revenue, JAN))  # pyrefly: ignore[bad-argument-type]
ctx.depends_on((total, JAN), (revenue, JAN))  # pyrefly: ignore[bad-argument-type]
ctx.path_to((costs, JAN), revenue)  # pyrefly: ignore[bad-argument-type]
