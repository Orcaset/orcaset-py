import pytest
from typing import cast

from orcaset import Formula


def test_formula_arithmetic_dunders_with_formulas_and_scalars():
    a = Formula.pure(10.0)
    b = Formula.pure(3.0)

    assert (-a).eval() == -10.0
    assert (a + b).eval() == 13.0
    assert (a + 2.0).eval() == 12.0
    assert (2.0 + a).eval() == 12.0
    assert (a - b).eval() == 7.0
    assert (20.0 - b).eval() == 17.0
    assert (a * b).eval() == 30.0
    assert (2.0 * b).eval() == 6.0


def test_formula_division_dunders():
    a = Formula.pure(10.0)
    b = Formula.pure(4.0)

    assert (a / b).eval() == 2.5
    assert (20.0 / b).eval() == 5.0
    assert (a // b).eval() == 2.0
    assert (20.0 // b).eval() == 5.0


def test_formula_arithmetic_propagates_none():
    value = Formula.pure(None)

    assert (-value).eval() is None
    assert (value + 1.0).eval() is None
    assert (1.0 + value).eval() is None
    assert (value - 1.0).eval() is None
    assert (1.0 - value).eval() is None
    assert (value * 2.0).eval() is None
    assert (2.0 * value).eval() is None
    assert (value / 2.0).eval() is None
    assert (2.0 / value).eval() is None
    assert (value // 2.0).eval() is None
    assert (2.0 // value).eval() is None


def test_formula_supports_builtin_sum():
    values = [Formula.pure(1.0), Formula.pure(2.0), Formula.pure(3.0)]

    assert sum(values, Formula.pure(0.0)).eval() == 6.0


def test_formula_sequence_evaluates_formula_collection():
    values: list[Formula[float | None]] = [
        cast(Formula[float | None], Formula.pure(1.0)),
        Formula.pure(None),
        cast(Formula[float | None], Formula.pure(3.0)),
    ]

    assert Formula.sequence(values).eval() == (1.0, None, 3.0)


def test_formula_sequence_supports_empty_iterables():
    assert Formula.sequence([]).eval() == ()


def test_formula_sequence_can_map_collection_values():
    values: list[Formula[float | None]] = [
        cast(Formula[float | None], Formula.pure(1.0)),
        Formula.pure(None),
        cast(Formula[float | None], Formula.pure(3.0)),
    ]

    total = Formula.sequence(values).map(lambda vals: sum(value or 0.0 for value in vals))

    assert total.eval() == 4.0


def test_formula_division_by_zero_is_not_suppressed():
    with pytest.raises(ZeroDivisionError):
        (Formula.pure(1.0) / Formula.pure(0.0)).eval()
