# Agent instructions

## Linting and type checking

- Use **ruff** for linting and formatting (`uvx ruff format` / `uvx ruff check`; ruff is not installed in the venv). Run it over any modified Python files before finishing.
- Use **pyrefly** for type checking. All new and modified Python code must pass `pyrefly check` with no issues.
- `examples/` is excluded from the root config's `project-excludes`, so it is not covered by a bare `pyrefly check`. Check it explicitly with `pyrefly check -c pyrefly.toml examples/*.py`.
- Run tests with `uv run pytest`.
- Baseline is `0 errors (1 suppressed)`; the single suppression is a pre-existing `# type: ignore[zero_division]` in `tests/test_f.py`. Do not add more.

## Typing rules (strict)

- Do **not** use `typing.cast` / `cast(...)`.
- Do **not** use `# type: ignore`, `# pyrefly: ignore`, or any other comment or config that suppresses type errors.
- Do **not** weaken types to silence the checker (for example by introducing `Any` solely to avoid errors).
- Fix the underlying types or design until `pyrefly check` is clean.
- Series keys are bounded by the `Key` protocol (`__lt__`). Reach for a protocol bound rather than suppressing an operator error on a type variable.
- `F` is covariant, so `F[V]` widens to `F[Maybe[V]]` without a wrapper node. Do not add identity `map`s to change an answer's type.

## Design invariants

These are load-bearing; breaking one is silently wrong rather than loudly broken.

- **Memoize nodes, never values.** A series caches `F` nodes on itself (one per `keys()`, `select(q)`, `query(q)`); a `Context` caches values by node id. Never store a `Replay`, `CellReplay` or any evaluated result on a series — those are per-context state and must be constructed inside an `F` node's evaluation.
- **Construct each series once** and share it by reference. Node identity is object identity, so a rebuilt series is a different computation.
- **`query` is total; cells are not.** A cell exists only where data exists, so absence in a stream is the absence of a cell. `MISSING` appears only as an answer. Every `Reduce` must therefore be total on the empty selection, and every `Select` returns `()` out of coverage instead of raising.
- **Absence policies are explicit.** Consumers of an answer (view functions, combines, recursive cells, `resample`'s `resolve`) state `strict` / `propagate` / `fill` / `unwrap` / `or_else`. Prefer `strict` unless a neutral value is genuinely meaningful — `fill` turns a coverage bug into a plausible number.
- **Evidence lives at leaves.** Only `LeafSeries` has cells and a `select` audit view. `MapSeries` / `Map2Series` are cell-less views whose provenance is the child query nodes. Do not synthesize a stream for a view; use `resample` / `rekey` if a derived line genuinely needs cells.
- **Select, reduce and view functions are pure and inert.** Deterministic, never call `run`, and return original cell nodes on trivial paths (an unclipped pair, a fold of one) so shared cells stay shared graph nodes.
- **Keys are strictly increasing and hashable**, enforced as a stream is pulled. Key-merging functions must stay lazy — a merged view over an infinite series must still be enumerable up to a point.
- **Label every node.** `print_deps` is the debugging surface; an unlabeled node prints as a raw closure repr.
