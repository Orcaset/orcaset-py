# Deep F evaluation example
#
# ``F`` chains are evaluated by an iterative Free interpreter, so arbitrary
# Map/Bind depth is fine.
#
# Recursive line items are defined as cell streams: the previous cell is
# carried in generator state, so each cell references its predecessor
# directly (a linear graph) instead of rebuilding a lookup spine per access.

from collections.abc import Iterator

from orcaset import Context, F, Pure, Series, print_deps

# -------------------------------------------------------------------------------------------------
# Deep Map chain — used to blow the call stack; now evaluates iteratively.
value: F[int] = Pure(1)

for _ in range(10_000):
    value = value.map(lambda x: x + 1)

print("Value of 10,000th mapped value: ", value.run(Context()))


# -------------------------------------------------------------------------------------------------
# Recursive series: counter[n] = counter[n - 1] + 1
def counter_cells() -> Iterator[tuple[int, F[int]]]:
    cell: F[int] = Pure(1, label="Counter seed")
    n = 0
    while True:
        yield n, cell
        cell = cell.map(lambda x: x + 1)
        n += 1


counter = Series.from_cells(counter_cells, label="Counter")

ctx = Context()
print("\nSequence elements:")
print(counter.at(0).run(ctx))
print(counter.at(1).run(ctx))
print(counter.at(2).run(ctx))

print("\nDeep lookback (element 9,999):")
print(counter.at(9_999).run(ctx))

print("\nNode 2 deps:")
print_deps(ctx, counter.at(2))
