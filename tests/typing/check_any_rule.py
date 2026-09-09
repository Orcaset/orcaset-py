"""Positive inference and expected rejections for ``AnyRule``."""

from collections.abc import Hashable
from datetime import date
from typing import assert_type

from orcaset import AnyRule, Cell, KeyedCell, KeyedRule, Period, Rule, Series, exact

growth = Cell("growth", lambda: 0.1)
assert_type(growth, Cell[float])


def name_len(name: str) -> int:
    return len(name)


by_name = KeyedCell("by name", name_len)
assert_type(by_name, KeyedCell[str, int])

Q1 = Period(date(2025, 1, 1), date(2025, 4, 1))
amounts = Series.of("amounts", exact, [(Q1, 100.0)])


def take[K: Hashable](target: AnyRule[K]) -> AnyRule[K]:
    return target


unkeyed: AnyRule[str] = growth
named: AnyRule[str] = (by_name, "revenue")
period_cell: AnyRule[Period] = (amounts, Q1)

take(growth)
assert_type(take((by_name, "revenue")), AnyRule[str])
assert_type(take((amounts, Q1)), AnyRule[Period])


def needs_str(_target: AnyRule[str]) -> None:
    return None


needs_str(growth)
needs_str((by_name, "revenue"))

# A keyed rule is not a Rule; it must be paired with a key.
needs_str(by_name)  # pyrefly: ignore[bad-argument-type]
needs_str(amounts)  # pyrefly: ignore[bad-argument-type]

# The key type must match the KeyedRule's key parameter.
needs_str((by_name, 1))  # pyrefly: ignore[bad-argument-type]
needs_str((amounts, Q1))  # pyrefly: ignore[bad-argument-type]
needs_str((amounts, "Q1"))  # pyrefly: ignore[bad-argument-type]

wrong_key: AnyRule[str] = (by_name, 1)  # pyrefly: ignore[bad-assignment]
wrong_rule: AnyRule[Period] = (by_name, Q1)  # pyrefly: ignore[bad-assignment]
keyed_as_rule: AnyRule[str] = by_name  # pyrefly: ignore[bad-assignment]

# Bare KeyedRule / Rule annotations stay distinct from the alias.
rule_only: Rule[float] = growth
keyed_only: KeyedRule[str, int] = by_name
_ = (unkeyed, named, period_cell, rule_only, keyed_only)
