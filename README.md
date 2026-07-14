# Orcaset

This branch holds an experimental monadic verion of `orcaset`.

*Updated core interpreter to a true free monad system which eliminates the recursion errors by moving monad steps from recursive evaluation to an explicit stack.*

Clone project and check out this branch:

```sh
git clone -b ref-monadic https://github.com/Orcaset/orcaset-py.git
```

## Examples

- [recursion_err](./examples/recursion_err.py): Deep chaining (no longer causes recursion errors)
- [recurse_spans](./examples/recurse_spans.py): Builds a sequence of growth spans using recursion
- [capex](./examples/capex.py): Maps capex > amort schedules by cohort > total amort sequences