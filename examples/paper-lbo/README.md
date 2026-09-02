# Paper LBO

This example implements the Wharton Career Services paper LBO case with pro forma
financials, a circular average-debt interest calculation, sources and uses, returns,
and a two-variable IRR sensitivity.

The model uses `Series.unfold` for recursive operating lines, `Series.of` for finite
date-keyed cash flows, and domain-bound `ops.period` / `ops.date` constructors for
arithmetic. A local `cumulate` helper uses `scan_cells` to create a running debt balance.

The interest lookup supplies `seed=0.0` and `maybe_abs_distance` at the circular ending
debt demand. `Context` uses that cut to solve the fixed point. Sensitivities replace the
NaN

## Run

This is a standalone uv project using the repository checkout of orcaset.

```sh
cd examples/paper-lbo
uv run python main.py
```

## References

| File | Role |
| --- | --- |
| [`references/wharton-lbo-practice-model.xlsx`](references/wharton-lbo-practice-model.xlsx) | Original practice workbook. |
| [`references/example-opus-excel-build-script.py`](references/example-opus-excel-build-script.py) | Reference Excel build script. |
| [`references/example-sol-excel-build-script.mjs`](references/example-sol-excel-build-script.mjs) | Reference Excel build script. |
| [`references/automated-excel-agent-example.xlsx`](references/automated-excel-agent-example.xlsx) | Reference agent-built workbook. |
