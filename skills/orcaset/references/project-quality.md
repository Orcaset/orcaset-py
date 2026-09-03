# Project quality

## Scale the layout to the model

A focused task may use one complete module. Split a larger model by dependency layer or economic domain, not into tiny files that obscure the graph:

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
│   └── reporting.py
├── main.py
└── tests/
```

Keep assumptions and timeline definitions low in the import graph. Domain modules should export named Orcaset nodes. Model definition may create rules, series, and lazy chains at import time; contexts, resolved values, printing, network calls, and output files belong in an entrypoint, report function, leaf thunk, or tests as appropriate.

Prefer exports from `orcaset.__all__`; do not depend on underscored internals or on legacy names that remain importable only as implementation residue. The API is experimental, so inspect the installed version and changelog before using remembered constructors. The unfold core uses generic `Series` rather than specialized `PeriodSeries`/`DateSeries`, and it does not provide the old statement, formatter, `Replayable`, `CellStream`, or value-level `scan` APIs.

## Static quality

Use Python 3.14+ syntax, including PEP 695 type parameters and aliases. Prefer Pyrefly and the repository's existing configuration. If creating a project, enable strict checking appropriate to its dependency surface, including implicit-`Any` reporting.

A clean result obtained through a workaround is not a clean model. Do not use:

- `typing.cast` as a static fix;
- explicit or implicit `Any` in model code;
- `type: ignore`, checker suppression comments, or disabled errors;
- unknown values flowing through formulas;
- broad unions that hide incompatible keys or answers.

Fix generic parameters, query signatures, `Maybe` narrowing, unfold state, and dependency structure at their source. `isna` narrows a `Maybe[V]`; prefer it to a cast. Give reusable helpers complete `Series[K, V, W]`, `Cells[K, V]`, `Effect[V]`, `Thunk[V]`, and callable annotations.

## Completion checks

Run the formatter, configured type checker, tests, and executable model when requested. Then verify observable invariants:

- required exports are Orcaset nodes with the promised key and answer types;
- finite and infinite chains terminate or advance as intended;
- key-only walks do not force cell values;
- all required inputs resolve while intentional misses remain `Na`;
- partial periods, off-spine queries, and continuation seams follow the declared query policy;
- derived lines reconcile to their components;
- balances reconcile opening value plus signed movements to ending value;
- schedules reconcile source amount, allocations, and residual value;
- scenario `Cell` changes affect dependents in a fresh context;
- dependency traces contain the expected upstream rules and structural traces explain any domain-sensitive behavior.

Test a small representative horizon first: the first recursive cell, an ordinary later cell, a miss, each important boundary, and any cycle. For chain operations, separately test the advertised keys and values so accidental forcing, clipping, gaps, or merge errors are visible.
