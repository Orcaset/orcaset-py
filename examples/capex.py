from __future__ import annotations

from orcaset import Cons, Empty, F, Period, Seq, Span, Context, empty, print_edges
from datetime import date
from dateutil.relativedelta import relativedelta

type SeqF[T] = Seq[F[T]]


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


first_cohort = amort_detail.bind(
    lambda s: s.head if isinstance(s, Cons) else F.pure(empty()),
    label="First cohort",
)
first_cohort_value = first_cohort.bind(
    lambda x: x.head.value if isinstance(x, Cons) else F.pure(0.0)
)

ctx = Context()
print(first_cohort_value.run(ctx))
print("\n\n")
print_edges(ctx)
