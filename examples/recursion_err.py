# Examples of recursion errors

from orcaset import Cons, Context, F, Pure, Seq, print_deps

# -------------------------------------------------------------------------------------------------
# Map explosion example
# `F.eval` is resolved recursively, not iteratively, so node depth can blow up the stack.
# Simple example of a RecursionError from this approach
# Depth of >1000 easily achievable for even mid-sized models
value = Pure(1)

for i in range(1000):
    value = value.map(lambda x: x + 1)

ctx = Context()

# This fails for i == 1000
print(value.run(ctx))

# Print dependency edges
# print_deps(ctx, value)


# -------------------------------------------------------------------------------------------------
# Sequence explosion example
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


first = nth(seq, 0)
second = nth(seq, 1)

ctx = Context()

# Print dependencies for the first, second, and third sequence elements
# print("First node deps:")
# print_deps(ctx, first)
# print("\nSecond node deps:")
# print_deps(ctx, second)
# print("\nThird node deps:")
# print_deps(ctx, nth(seq, 2))

# This blows up
# `Seq.tail` is defined by a recursive index-based lookback via `nth`.
# The `bind` operation in `nth` creates a new object with a new ID on each call.
# This means that calling `nth(seq, i)` walks up a new bind sequence to element `i - 1` at each step `i`.
# Results in quadratic(?) complexity.

# print("\nGetting even a semi-far out element results in a RecursionError:")
# try:
#     print_deps(ctx, nth(seq, 40))
# except RecursionError as e:
#     raise e
