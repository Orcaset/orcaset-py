# Deep F evaluation example
#
# ``F`` chains are evaluated by an iterative Free interpreter, so arbitrary
# Map/Bind depth is fine.
#
# Recursive line items query themselves: counter[n] = counter[n - 1] + 1 is
# written as ``counter.query(n - 1)``. Query nodes are memoized per
# (series, query), so the lookback chain is a linear graph — evaluated
# iteratively, cached per context.

from collections.abc import Iterator

from orcaset import Context, F, LeafSeries, Pure, exact, only, print_deps, unwrap

# -------------------------------------------------------------------------------------------------
# Deep Map chain — used to blow the call stack; now evaluates iteratively.
value: F[int] = Pure(1)

for _ in range(10_000):
    value = value.map(lambda x: x + 1)

print("Value of 10,000th mapped value: ", value.run(Context()))


# -------------------------------------------------------------------------------------------------
# Recursive series: counter[n] = counter[n - 1] + 1
def counter_cells() -> Iterator[tuple[int, F[int]]]:
    yield 0, Pure(1, label="Counter seed")
    n = 1
    while True:
        yield n, counter.query(n - 1).map(lambda a: unwrap(a) + 1, label=f"Counter@{n}")
        n += 1


counter = LeafSeries.from_cells(counter_cells, exact(), only(), label="Counter")

ctx = Context()
print("\nSequence elements:")
print(counter.query(0).run(ctx))
print(counter.query(1).run(ctx))
print(counter.query(2).run(ctx))

print("\nDeep lookback (element 9,999):")
print(counter.query(9_999).run(ctx))

print("\nNode 2 deps:")
print_deps(ctx, counter.query(2))
