"""Lease types, rollover costs, and expense reimbursements."""

from collections.abc import Callable, Generator
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from dateutil.relativedelta import relativedelta
from orcaset import (
    YF,
    Chain,
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


def accrue_or_zero(
    q: Period, cells: Chain[Period, Maybe[float]]
) -> Effect[Maybe[float]]:
    result = query.accrue(YF.cmonthly)(q, cells)
    if isinstance(result, Generator):
        result = yield from result
    return maybe.value_or(result, 0.0)


class LeaseType(StrEnum):
    FULL_SERVICE = "FS"
    SINGLE_NET = "N"
    TRIPLE_NET = "NNN"


renewal_probability = Val("Renewal probability", 0.70)
downtime_months = Val("Non-renewal downtime months", 6.0)
new_free_months = Val("New lease free rent months", 6.0)
renewal_free_months = Val("Renewal free rent months", 3.0)
new_ti_psf = Val("New lease TI / RSF", 10.0)
renewal_ti_psf = Val("Renewal TI / RSF", 3.0)
new_lc_pct = Val("New lease commission %", 0.03)
renewal_lc_pct = Val("Renewal commission %", 0.01)
lease_term = Val("New and renewal lease term", 10)


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
    suite_rsf = Val(f"{name} RSF", area)
    start_date = Val(f"{name} start", start)
    expiry = Val(f"{name} lease expiration", expiration)

    def occupancy_window() -> Effect[tuple[tuple[Period, float], ...]]:
        begin = yield from get(start_date)
        end = (
            date.max
            if extension_life is None
            else (yield from get(expiry)) + extension_life
        )
        return ((Period(begin, end), (yield from get(suite_rsf))),)

    occupied = Series[Period, float, Maybe[float]].of(
        f"{name} occupied RSF",
        query.avg_or(YF.cmonthly, fill=0.0),
        Fn(f"{name} occupancy window", occupancy_window),
    )
    rent_psf = growing_line(
        f"{name} rent / RSF", Val(f"{name} FY25 rent / RSF", initial_rent), rent_growth
    )
    rent = ops.mul(f"{name} rent", rent_psf, occupied, merge_keys=period_union)

    def expiration_seed() -> Effect[date | None]:
        return (yield from get(expiry))

    @Series[Period, Maybe[float], Maybe[float]].define(
        f"{name} turnover vacancy",
        accrue_or_zero,
        seed=Thunk(expiration_seed),
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
        f"{name} free rent",
        accrue_or_zero,
        seed=Thunk(expiration_seed),
    )
    def free_rent(
        expiration_date: date | None,
    ) -> Effect[tuple[Period, Maybe[float], date | None] | None]:
        if expiration_date is None:
            return None
        free_rent_period = Period(expiration_date, expiration_date + year_offset)
        probability = yield from get(renewal_probability)
        months = (1.0 - probability) * (
            yield from get(new_free_months)
        ) + probability * (yield from get(renewal_free_months))
        return (
            free_rent_period,
            maybe.mul_some((yield from get_at(rent, free_rent_period)), months / 12),
            None,
        )

    @Series[Period, Maybe[float], Maybe[float]].define(
        f"{name} tenant improvements",
        accrue_or_zero,
        seed=Thunk(expiration_seed),
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
        f"{name} leasing commissions",
        accrue_or_zero,
        seed=Thunk(expiration_seed),
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
            f"{name} occupied share",
            occupied,
            Fn(f"{name} / property RSF", lambda: 1.0 / (yield from get(rsf))),
        )
        gross = ops.mul(
            f"{name} reimbursements before downtime",
            expenses,
            share,
            merge_keys=period_union,
        )

        @Series[Period, Maybe[float], Maybe[float]].define(
            f"{name} reimbursement downtime",
            accrue_or_zero,
            seed=Thunk(expiration_seed),
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
                maybe.mul_some(
                    (yield from get_at(gross, downtime_period)), 1.0 - probability
                ),
                None,
            )

        return ops.sub(
            f"{name} reimbursements",
            gross,
            downtime_loss,
            merge_keys=period_union,
        )

    match lease_type:
        case LeaseType.FULL_SERVICE:
            reimbursements = Series[Period, Maybe[float], Maybe[float]].of(
                f"{name} reimbursements", accrue_or_zero, ()
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
