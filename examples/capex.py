# Create a model with following structure:
# Capex: Series of spans representing capital expenditures
# Amort detail: Nested sequence of sequence of spans representing amortization detail for each capex span
# Total amort: Period-aligned merge-sum of all amort detail cohorts
#
# Output summary:
# Period end        2026-12-31  2027-12-31  2028-12-31  2029-12-31
# Capex                    100         200           0           0
#
# Amort cohort 1             0          50          50           0
# Amort cohort 2             0           0         100          100
#
# Total amort                0          50         150          100

from __future__ import annotations

from orcaset import Cons, Empty, F, Period, Seq, Span, Context, empty
from datetime import date
from dateutil.relativedelta import relativedelta


# CAPEX
input_periods = [
    Period(date(2025, 12, 31), date(2026, 12, 31)),
    Period(date(2026, 1, 1), date(2027, 12, 31)),
]


capex_raw: Seq[F[Span[float]]] = Cons(
    F.pure(Span(input_periods[0], F.pure(100)), label="Capex expense 100"),
    F.delay(
        lambda: Cons(
            F.pure(Span(input_periods[1], F.pure(200)), label="Capex expense 200"),
            F.pure(empty()),
        )
    ),
)
capex = F.pure(capex_raw, label="Pure capex")


# AMORT DETAIL
def schedule_amort(exp: Span[float]) -> Seq[Span[float]]:
    return Cons(
        Span(
            Period(exp.period.end, exp.period.end + relativedelta(years=1)),
            exp.value.map(lambda x: x / 2),
        ),
        F.delay(
            lambda: Cons(
                Span(
                    Period(
                        exp.period.end + relativedelta(years=1),
                        exp.period.end + relativedelta(years=2),
                    ),
                    exp.value.map(lambda x: x / 2),
                ),
                F.pure(empty()),
            )
        ),
    )


def map_amort_detail(s: Seq[F[Span[float]]]) -> Seq[F[Seq[Span[float]]]]:
    if isinstance(s, Empty):
        return empty()
    return Cons(
        s.head.map(schedule_amort, label="Cohort detail"),
        s.tail.map(map_amort_detail),
    )


amort_detail: F[Seq[F[Seq[Span[float]]]]] = capex.map(map_amort_detail, label="Amort detail")


# TOTAL AMORTIZATION
def add_schedules(a: Seq[Span[float]], b: Seq[Span[float]]) -> Seq[Span[float]]:
    """Merge two period-sorted amort schedules, summing values on equal periods."""
    if isinstance(a, Empty):
        return b
    if isinstance(b, Empty):
        return a

    a_span, b_span = a.head, b.head
    if a_span.period == b_span.period:
        return Cons(
            Span(
                a_span.period,
                a_span.value.bind(lambda x: b_span.value.map(lambda y: x + y)),
            ),
            a.tail.bind(lambda at: b.tail.map(lambda bt: add_schedules(at, bt))),
        )
    if a_span.period.start < b_span.period.start:
        return Cons(a_span, a.tail.map(lambda at: add_schedules(at, b)))
    return Cons(b_span, b.tail.map(lambda bt: add_schedules(a, bt)))


def sum_amort_detail(cohorts: Seq[F[Seq[Span[float]]]]) -> F[Seq[Span[float]]]:
    if isinstance(cohorts, Empty):
        return F.pure(empty())
    rest_total = cohorts.tail.bind(sum_amort_detail)
    return cohorts.head.bind(
        lambda sched: rest_total.map(lambda rest: add_schedules(sched, rest)),
        label="Sum amort cohorts",
    )


total_amort: F[Seq[Span[float]]] = amort_detail.bind(sum_amort_detail, label="Total amort")


# OUTPUT

ctx = Context()


## Capex
def nth[T](s: Seq[F[T]], n: int) -> F[T]:
    """Get the nth F-headed element, forcing tails through the F cache."""
    if not isinstance(s, Cons):
        raise IndexError(f"sequence has no item at index {n}")
    if n == 0:
        return s.head
    return s.tail.bind(lambda rest: nth(rest, n - 1))


print(f"\n{'-' * 16}\nCapex:\n")
for i in range(2):
    span = capex.bind(lambda s, i=i: nth(s, i), label=f"Capex span {i}")
    value = span.bind(lambda sp: sp.value, label=f"Capex value {i}")
    print(f"[{i}] {span.run(ctx).period} = {value.run(ctx)}")


## Amortization schedules
def nth_span(s: Seq[Span[float]], n: int) -> F[Span[float]]:
    """Helper to get the nth span from a sequence of spans."""
    if not isinstance(s, Cons):
        raise IndexError(f"sequence has no item at index {n}")
    if n == 0:
        return F.pure(s.head)
    return s.tail.bind(lambda rest: nth_span(rest, n - 1))


print(f"\n{'-' * 16}\nAmort detail:\n")
for i in range(2):
    cohort = amort_detail.bind(lambda s, i=i: nth(s, i), label=f"Amort cohort {i}")
    print(f"Cohort {i}:")
    for j in range(2):
        span = cohort.bind(
            lambda s, j=j: nth_span(s, j),
            label=f"Amort detail span {i}.{j}",
        )
        value = span.bind(lambda sp: sp.value, label=f"Amort detail value {i}.{j}")
        print(f"  [{j}] {span.run(ctx).period} = {value.run(ctx)}")
    print()


## Total amortization
print(f"\n{'-' * 16}\nTotal amortization:\n")
for i in range(3):
    span = total_amort.bind(lambda s, i=i: nth_span(s, i), label=f"Total amort span {i}")
    value = span.bind(lambda sp: sp.value, label=f"Total amort value {i}")
    print(f"[{i}] {span.run(ctx).period} = {value.run(ctx)}")
