# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

import calendar
from collections.abc import Callable
from datetime import date
from typing import Self


####################
# Date functions
def is_month_end(dt: date):
    return dt.day == calendar.monthrange(dt.year, dt.month)[1]


####################
# Year fraction function annotations
class YF:
    """Common year fraction functions."""

    class _NA:
        def __call__(self, _: date, __: date) -> float:
            raise NotImplementedError(
                "No valid YF function. This may be the result of combining Accruals with different year fractions."
            )

        def __repr__(self):
            return "YF.na"

        def __deepcopy__(self, _: object) -> Self:
            return self

    class _Actual360:
        def __call__(self, dt1: date, dt2: date) -> float:
            return (dt2 - dt1).days / 360

        def __repr__(self):
            return "YF.act360"

        def __deepcopy__(self, _: object) -> Self:
            return self

    class _Thirty360:
        def __call__(self, dt1: date, dt2: date) -> float:
            """
            Returns the fraction of a year between `dt1` and `dt2` on 30 / 360 day count basis.
            """
            # Based on this answer https://stackoverflow.com/a/62232820/18582661
            # swap so dt1 is always before dt2
            flipped = 1
            if dt1 > dt2:
                dt1, dt2 = dt2, dt1
                flipped = -1

            y1, m1, d1 = dt1.year, dt1.month, dt1.day
            y2, m2, d2 = dt2.year, dt2.month, dt2.day

            if (m2 == 2 and is_month_end(dt2)) and (m1 == 2 and is_month_end(dt1)):
                d2 = 30
            if d2 == 31 and d1 >= 30:
                d2 = 30
            if d1 == 31:
                d1 = 30
            if m1 == 2 and is_month_end(dt1):
                d1 = 30

            days = (d2 + m2 * 30 + y2 * 360) - (d1 + m1 * 30 + y1 * 360)
            return days / 360 * flipped

        def __repr__(self):
            return "YF.thirty360"

        def __deepcopy__(self, _: object) -> Self:
            return self

    class _CMonthly:
        def __call__(self, dt1: date, dt2: date) -> float:
            """
            Year fraction from but excluding `dt1` to and including `dt2` where each calendar
            month is 1/12th of a year.
            Partial calendar months are treated as actual days elapsed over actual days in the month.

            Example:
            >>> YF.cmonthly(date(2020, 1, 31), date(2020, 2, 29))
            0.08333333333333333
            >>> # Not equal to 1/12th of a year because June and July have different number of days
            >>> # equals [(29/30) + (1/31)] / 12
            >>> YF.cmonthly(date(2020, 6, 1), date(2020, 7, 1))
            0.0832437275985663
            """
            # swap so dt1 is always before dt2
            flipped = 1
            if dt1 > dt2:
                dt1, dt2 = dt2, dt1
                flipped = -1

            y1, m1, d1 = dt1.year, dt1.month, dt1.day
            y2, m2, d2 = dt2.year, dt2.month, dt2.day

            # year frac assuming whole months
            year_month_frac = ((y2 * 360 + m2 * 30) - (y1 * 360 + m1 * 30)) / 360

            # year frac of starting month stub in range (if any)
            start_month_last_day = calendar.monthrange(y1, m1)[1]
            start_stub = (start_month_last_day - d1) / start_month_last_day

            # year frac of ending month stub *NOT* in range (if any)
            end_month_last_day = calendar.monthrange(y2, m2)[1]
            end_stub = (end_month_last_day - d2) / end_month_last_day

            return (year_month_frac + (start_stub - end_stub) / 12) * flipped

        def __repr__(self):
            return "YF.cmonthly"

        def __deepcopy__(self, _: object) -> Self:
            return self

    act360 = _Actual360()

    thirty360 = _Thirty360()

    cmonthly = _CMonthly()

    na = _NA()


type YfType = Callable[[date, date], float] | YF._Actual360 | YF._CMonthly | YF._Thirty360
