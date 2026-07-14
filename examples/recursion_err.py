# Deep F evaluation example
#
# Previously ``F`` was forced recursively, so chains deeper than ~1000 raised
# RecursionError. Evaluation is now an iterative Free interpreter, so arbitrary
# Map/Bind depth is fine.
#
# The Seq ``nth`` performance issue remains.

from orcaset import Cons, Context, F, Pure, Seq, print_deps

# -------------------------------------------------------------------------------------------------
# Deep Map chain — used to blow the call stack; now evaluates iteratively.
value: F[int] = Pure(1)

for _ in range(10_000):
    value = value.map(lambda x: x + 1)

ctx = Context()
print("Value of 10,000th mapped value: ", value.run(ctx))


# -------------------------------------------------------------------------------------------------
# Sequence lookback example (construction footgun; not a recursion-limit issue anymore)
def nth[T](s: Seq[F[T]], n: int) -> F[T]:
    """Return the nth F-headed element, forcing tails through the F cache."""
    if n < 0:
        raise IndexError(f"sequence has no item at index {n}")

    if not isinstance(s, Cons):
        raise IndexError(f"sequence has no item at index {n}")

    if n == 0:
        return s.head

    return s.tail.bind(lambda rest: nth(rest, n - 1))


def next_cons(index: int) -> F[Seq[F[int]]]:
    return F.delay(
        lambda: Cons(head=nth(seq, index - 1).map(lambda x: x + 1), tail=next_cons(index + 1))
    )


def make_seq() -> Seq[F[int]]:
    return Cons(head=Pure(1), tail=next_cons(1))


seq = make_seq()

# ``nth`` still builds a Bind chain of length n (large graphs / quadratic lookback).
print("\nSequence elements:")
print(nth(seq, 0).run(Context()))
print(nth(seq, 1).run(Context()))
print(nth(seq, 2).run(Context()))

print("\nSequence element deps:")
print("\nNode 0 deps:")
print_deps(ctx, nth(seq, 0))
print("\nNode 1 deps:")
print_deps(ctx, nth(seq, 1))
print("\nNode 2 deps:")
print_deps(ctx, nth(seq, 2))
