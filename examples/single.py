from orcaset import F, Pure, Context, print_deps, Seq, Cons


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
print("First node deps:")
print_deps(ctx, first)
print(f"Eval count: {ctx.eval_count}")
print("\nSecond node deps:")
print_deps(ctx, second)
print(f"Eval count: {ctx.eval_count}")
print("\nThird node deps:")
print_deps(ctx, nth(seq, 2))
print(f"Eval count: {ctx.eval_count}")
print("\nThird node deps again:")
print_deps(ctx, nth(seq, 2))

# print("\100th node deps:")
# print_deps(ctx, nth(seq, 4))
