"""Lease types, rollover costs, and expense reimbursements."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from dateutil.relativedelta import relativedelta

from orcaset import (
    YF,
    Effect,
    Fn,
    Maybe,
    Period,
    Rule,
    Series,
    Thunk,
    Val,
    get,
    get_at,
    maybe,
    ops,
    period_union,
    query,
)

type Amount = Series[Period, Maybe[float], Maybe[float]]
type Occupancy = Series[Period, float, Maybe[float]]
type Growth = Series[Period, float, Maybe[float]]
type GrowingLine = Callable[[str, Rule[float], Growth], Amount]


class LeaseType(StrEnum):
    FULL_SERVICE = "FS"
    SINGLE_NET = "N"
    TRIPLE_NET = "NNN"


renewal_probability = Val(0.70, name="Renewal probability")
downtime_months = Val(6.0, name="Non-renewal downtime months")
new_free_months = Val(6.0, name="New lease free rent months")
renewal_free_months = Val(3.0, name="Renewal free rent months")
new_ti_psf = Val(10.0, name="New lease TI / RSF")
renewal_ti_psf = Val(3.0, name="Renewal TI / RSF")
new_lc_pct = Val(0.03, name="New lease commission %")
renewal_lc_pct = Val(0.01, name="Renewal commission %")
lease_term = Val(10, name="New and renewal lease term")


@dataclass(frozen=True)
class Lease:
    name: str
    lease_type: LeaseType
    area: Occupancy
    suite_rsf: Val[float]
    start: Val[date]
    expiration: Val[date]
    rent_growth: Growth
    rent_psf: Amount
    rent: Amount
    turnover_vacancy: Amount
    free_rent: Amount
    improvements: Amount
    commissions: Amount
    reimbursements: Amount


def lease(
    name: str,
    lease_type: LeaseType,
    area: float,
    expiration: date,
    initial_rent: float,
    rent_growth: Growth,
    *,
    start: date,
    extension_life: relativedelta | None = None,
    year_offset: relativedelta,
    rsf: Rule[float],
    property_taxes: Amount,
    reimbursable_expenses: Amount,
    growing_line: GrowingLine,
) -> Lease:
    """Occupancy covers ``start`` to expiration plus ``extension_life``, or ``date.max`` if omitted."""
    suite_rsf = Val(area, name=f"{name} RSF")
    start_date = Val(start, name=f"{name} start")
    expiry = Val(expiration, name=f"{name} lease expiration")

    def occupancy_window() -> Effect[tuple[tuple[Period, float], ...]]:
        begin = yield from get(start_date)
        end = date.max if extension_life is None else (yield from get(expiry)) + extension_life
        return ((Period(begin, end), (yield from get(suite_rsf))),)

    occupied = Series[Period, float, Maybe[float]].of(
        query.avg_fill(YF.cmonthly, fill=0.0),
        Fn(occupancy_window, name=f"{name} occupancy window"),
        name=f"{name} occupied RSF",
    )
    rent_psf = growing_line(
        f"{name} rent / RSF", Val(initial_rent, name=f"{name} FY25 rent / RSF"), rent_growth
    )
    rent = ops.mul(rent_psf, occupied, merge_keys=period_union, name=f"{name} rent")

    def expiration_seed() -> Effect[date | None]:
        return (yield from get(expiry))

    @Series[Period, Maybe[float], Maybe[float]].define(
        query.accrue_drop(YF.cmonthly),
        seed=Thunk(expiration_seed),
        name=f"{name} turnover vacancy",
    )
    def vacancy(
        expiration_date: date | None,
    ) -> Effect[tuple[Period, Maybe[float], date | None] | None]:
        if expiration_date is None:
            return None
        vacancy_period = Period(expiration_date, expiration_date + year_offset)
        probability = yield from get(renewal_probability)
        months = yield from get(downtime_months)
        return (
            vacancy_period,
            maybe.mul_some(
                (yield from get_at(rent, vacancy_period)),
                (1.0 - probability) * months / 12,
            ),
            None,
        )

    @Series[Period, Maybe[float], Maybe[float]].define(
        query.accrue_drop(YF.cmonthly),
        seed=Thunk(expiration_seed),
        name=f"{name} free rent",
    )
    def free_rent(
        expiration_date: date | None,
    ) -> Effect[tuple[Period, Maybe[float], date | None] | None]:
        if expiration_date is None:
            return None
        free_rent_period = Period(expiration_date, expiration_date + year_offset)
        probability = yield from get(renewal_probability)
        months = (1.0 - probability) * (yield from get(new_free_months)) + probability * (
            yield from get(renewal_free_months)
        )
        return (
            free_rent_period,
            maybe.mul_some((yield from get_at(rent, free_rent_period)), months / 12),
            None,
        )

    @Series[Period, Maybe[float], Maybe[float]].define(
        query.accrue_drop(YF.cmonthly),
        seed=Thunk(expiration_seed),
        name=f"{name} tenant improvements",
    )
    def improvements(
        expiration_date: date | None,
    ) -> Effect[tuple[Period, Maybe[float], date | None] | None]:
        if expiration_date is None:
            return None
        improvement_period = Period(expiration_date, expiration_date + year_offset)
        probability = yield from get(renewal_probability)
        cost = (1.0 - probability) * (yield from get(new_ti_psf)) + probability * (
            yield from get(renewal_ti_psf)
        )
        return improvement_period, cost * (yield from get(suite_rsf)), None

    @Series[Period, Maybe[float], Maybe[float]].define(
        query.accrue_drop(YF.cmonthly),
        seed=Thunk(expiration_seed),
        name=f"{name} leasing commissions",
    )
    def commissions(
        expiration_date: date | None,
    ) -> Effect[tuple[Period, Maybe[float], date | None] | None]:
        if expiration_date is None:
            return None
        commission_period = Period(expiration_date, expiration_date + year_offset)
        probability = yield from get(renewal_probability)
        rate = (1.0 - probability) * (yield from get(new_lc_pct)) + probability * (
            yield from get(renewal_lc_pct)
        )
        return (
            commission_period,
            maybe.mul_some(
                (yield from get_at(rent, commission_period)),
                rate * (yield from get(lease_term)),
            ),
            None,
        )

    def reimbursed(expenses: Amount) -> Amount:
        share = ops.scale(
            occupied,
            Fn(lambda: 1.0 / (yield from get(rsf)), name=f"{name} / property RSF"),
            name=f"{name} occupied share",
        )
        gross = ops.mul(
            expenses,
            share,
            merge_keys=period_union,
            name=f"{name} reimbursements before downtime",
        )

        @Series[Period, Maybe[float], Maybe[float]].define(
            query.accrue_drop(YF.cmonthly),
            seed=Thunk(expiration_seed),
            name=f"{name} reimbursement downtime",
        )
        def downtime_loss(
            expiration_date: date | None,
        ) -> Effect[tuple[Period, Maybe[float], date | None] | None]:
            if expiration_date is None:
                return None
            months = yield from get(downtime_months)
            downtime_period = Period(
                expiration_date, expiration_date + relativedelta(months=int(months))
            )
            probability = yield from get(renewal_probability)
            return (
                downtime_period,
                maybe.mul_some((yield from get_at(gross, downtime_period)), 1.0 - probability),
                None,
            )

        return ops.sub(
            gross,
            downtime_loss,
            merge_keys=period_union,
            name=f"{name} reimbursements",
        )

    match lease_type:
        case LeaseType.FULL_SERVICE:
            reimbursements = Series[Period, Maybe[float], Maybe[float]].empty(
                query.accrue_drop(YF.cmonthly), name=f"{name} reimbursements"
            )
        case LeaseType.SINGLE_NET:
            reimbursements = reimbursed(property_taxes)
        case LeaseType.TRIPLE_NET:
            reimbursements = reimbursed(reimbursable_expenses)

    return Lease(
        name,
        lease_type,
        occupied,
        suite_rsf,
        start_date,
        expiry,
        rent_growth,
        rent_psf,
        rent,
        vacancy,
        free_rent,
        improvements,
        commissions,
        reimbursements,
    )
