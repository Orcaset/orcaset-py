# Build a sequence of spans using a recursive function.

from __future__ import annotations

from datetime import date

from dateutil.relativedelta import relativedelta

from orcaset import Cons, Context, F, Period, Seq, Span, print_deps

type SpanSeq[T] = Seq[F[Span[T]]]


def nth[T](s: Seq[F[T]], n: int) -> F[T]:
    """Return the nth F-headed element, forcing tails through the F cache."""
    if n < 0:
        raise IndexError(f"sequence has no item at index {n}")

    if not isinstance(s, Cons):
        raise IndexError(f"sequence has no item at index {n}")

    if n == 0:
        return s.head

    return s.tail.bind(lambda rest: nth(rest, n - 1))


def next_span[T: int | float](prior: Span[T]) -> Span[float]:
    return Span(
        Period(
            prior.period.start + relativedelta(years=1),
            prior.period.end + relativedelta(years=1),
        ),
        prior.value.map(lambda value: value * 1.1, label="Revenue growth at 10%"),
    )


def next_cons(index: int = 1) -> F[SpanSeq[float]]:
    return F.delay(
        lambda: Cons(
            head=revenue.bind(
                lambda spans: nth(spans, index - 1),
                label=f"Revenue span {index - 1}",
            ).map(next_span, label=f"Revenue span {index}"),
            tail=next_cons(index + 1),
        ),
        label=f"Revenue cons {index}",
    )


initial_value: F[Span[float]] = F.pure(
    Span(
        Period(date(2025, 12, 31), date(2026, 12, 31)),
        F.pure(100.0, label="Initial revenue value"),
    ),
    label="Initial revenue span",
)


revenue: F[SpanSeq[float]] = F.pure(
    Cons(
        head=initial_value,
        tail=next_cons(1),
    ),
    label="Revenue",
)


# Print dependencies for the third revenue span and value
ctx = Context()

third_span = revenue.bind(lambda spans: nth(spans, 2), label="Third revenue span")
third_value = third_span.bind(lambda span: span.value, label="Third revenue value")

print(third_span.run(ctx))
print(third_value.run(ctx))
print("\n\n")
print_deps(ctx, third_value)
