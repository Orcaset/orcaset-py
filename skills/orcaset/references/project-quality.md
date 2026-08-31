# Project quality

## Scale the layout to the model

A focused task may use one complete module. Split a larger model by dependency
layer or economic domain, not into tiny files that obscure the graph:

```text
project/
├── pyproject.toml
├── pyrefly.toml
├── src/model/
│   ├── assumptions.py
│   ├── timeline.py
│   ├── operations.py
│   ├── schedules.py
│   ├── financing.py
│   └── statements.py
├── main.py
└── tests/
```

Keep assumptions and timeline definitions low in the import graph. Domain
modules should export named Orcaset nodes. Re-export required public model
objects from the requested entrypoint or package surface. Avoid import-time
evaluation: model definition may create rules and series, while contexts,
materialized values, printing, and files belong in an entrypoint, report
function, or tests.

Prefer public imports from `orcaset`; do not depend on underscored internals.
The API is experimental, so inspect the installed version and its public type
signatures before assuming an older constructor or helper still exists.

## Static quality

Use Python 3.14+ syntax, including PEP 695 type parameters and aliases. Prefer
Pyrefly and the repository's existing configuration. If creating a project,
enable strict checking appropriate to its dependency surface, including
implicit-`Any` reporting.

A clean result obtained through a workaround is not a clean model. Do not use:

- `typing.cast` or runtime casts presented as static fixes;
- explicit or implicit `Any`;
- `type: ignore`, checker suppression comments, or disabled errors;
- unknown or untyped values allowed to flow through formulas;
- unnecessarily broad unions that hide incompatible keys or values.

Fix annotations, generic parameters, query return types, missing-value
narrowing, and dependency structure at their source. `isna` narrows a
`Maybe[V]`; prefer it to a cast.

## Completion checks

Run the formatter, configured type checker, tests, and the executable model if
one is requested. Then verify observable model invariants:

- required exports are Orcaset nodes of the intended surface;
- all required inputs resolve, while intended misses remain `Na`;
- partial periods and seams follow the declared query policy;
- derived lines reconcile to their displayed children;
- balances reconcile opening value plus movements to ending value;
- schedules reconcile source amount, allocations, and residual value;
- financing reconciles draws, repayments, payoff, and equity cash flows;
- scenario `Cell` changes alter dependent results in a fresh context;
- every public series is queried directly using its documented key type;
- dependency traces include the expected upstream rules.

Test a small representative horizon first, including the first recursive
period, a normal later period, a miss, and each important boundary. Add broader
horizons only after those checks are correct.
