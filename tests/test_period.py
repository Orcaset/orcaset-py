# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from collections.abc import Iterator
from datetime import date
from itertools import islice

from dateutil.relativedelta import relativedelta

from orcaset import Period, date_union, period_union


def test_period_union_splits_at_every_source_boundary():
    monthly = Period.seq(
        date(2026, 1, 1),
        relativedelta(months=1),
        date(2026, 4, 1),
    )
    quarterly = [Period(date(2026, 1, 1), date(2026, 4, 1))]

    assert list(period_union((monthly, quarterly))) == [
        Period(date(2026, 1, 1), date(2026, 2, 1)),
        Period(date(2026, 2, 1), date(2026, 3, 1)),
        Period(date(2026, 3, 1), date(2026, 4, 1)),
    ]


def test_period_union_omits_uncovered_gaps():
    domains = (
        [Period(date(2026, 1, 1), date(2026, 2, 1))],
        [Period(date(2026, 3, 1), date(2026, 4, 1))],
    )

    assert list(period_union(domains)) == [
        Period(date(2026, 1, 1), date(2026, 2, 1)),
        Period(date(2026, 3, 1), date(2026, 4, 1)),
    ]


def test_period_union_is_lazy_over_infinite_domains():
    monthly = Period.seq(date(2026, 1, 1), relativedelta(months=1))
    quarterly = Period.seq(date(2026, 1, 1), relativedelta(months=3))

    assert list(islice(period_union((monthly, quarterly)), 3)) == [
        Period(date(2026, 1, 1), date(2026, 2, 1)),
        Period(date(2026, 2, 1), date(2026, 3, 1)),
        Period(date(2026, 3, 1), date(2026, 4, 1)),
    ]


def test_date_union_merges_and_dedupes_ascending_domains():
    left = [date(2026, 1, 1), date(2026, 2, 1), date(2026, 4, 1)]
    right = [date(2026, 2, 1), date(2026, 3, 1)]

    assert list(date_union((left, right))) == [
        date(2026, 1, 1),
        date(2026, 2, 1),
        date(2026, 3, 1),
        date(2026, 4, 1),
    ]


def test_date_union_handles_empty_and_single_domains():
    assert list(date_union(())) == []
    assert list(date_union(([], []))) == []
    assert list(date_union(([date(2026, 1, 1), date(2026, 2, 1)],))) == [
        date(2026, 1, 1),
        date(2026, 2, 1),
    ]


def test_date_union_is_lazy_over_infinite_domains():
    def monthly_ends(start: date) -> Iterator[date]:
        current = start
        while True:
            yield current
            current += relativedelta(months=1)

    left = monthly_ends(date(2026, 1, 31))
    right = monthly_ends(date(2026, 1, 15))

    assert list(islice(date_union((left, right)), 4)) == [
        date(2026, 1, 15),
        date(2026, 1, 31),
        date(2026, 2, 15),
        date(2026, 2, 28),
    ]
