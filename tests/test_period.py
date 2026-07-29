# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from datetime import date
from itertools import islice

from dateutil.relativedelta import relativedelta

from orcaset import Period, period_union


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
