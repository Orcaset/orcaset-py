# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from operator import mul

from orcaset import Na, add_values, combine_values, isna


def test_combine_values_folds_non_na_values():
    assert combine_values((2, 3, 4), mul) == 24


def test_combine_values_propagates_na():
    assert isna(combine_values((2, Na, 4), mul))


def test_combine_values_returns_na_for_an_empty_tuple():
    assert isna(combine_values((), mul))


def test_add_values_adds_floats_and_propagates_na():
    assert add_values((1.25, 2.75)) == 4.0
    assert isna(add_values((1.0, Na)))
