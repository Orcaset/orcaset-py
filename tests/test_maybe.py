# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from operator import mul

from orcaset import Maybe, Na, add_some, combine_some, isna, multiply_some, some, value_or


def test_some_returns_value_as_maybe():
    value: Maybe[int] = some(3)
    assert value == 3


def test_value_or_returns_value_or_default():
    assert value_or(3, 0) == 3
    assert value_or(Na, 0) == 0


def test_combine_some_folds_non_na_values():
    assert combine_some((2, 3, 4), mul) == 24


def test_combine_some_propagates_na():
    assert isna(combine_some((2, Na, 4), mul))


def test_combine_some_returns_na_for_an_empty_tuple():
    empty: tuple[Maybe[int], ...] = ()
    assert isna(combine_some(empty, mul))


def test_add_some_adds_floats_and_propagates_na():
    assert add_some((1.25, 2.75)) == 4.0
    assert isna(add_some((1.0, Na)))
    assert isna(add_some(()))


def test_multiply_some_multiplies_floats_and_propagates_na():
    assert multiply_some((2.0, 3.0, 4.0)) == 24.0
    assert isna(multiply_some((2.0, Na)))
    assert isna(multiply_some(()))
