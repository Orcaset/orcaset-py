# Inputs, scenarios, units, and provenance

Use a `Val` for an input that should change between runs and a `Fn` for a calculated assumption. Read them through `get` in dependent computations, including structure-driving assumptions via a seed `Thunk`. Fixed constants need not all become nodes.

```python
growth.value = 0.025
scenario = Context()
result = scenario.get_at(revenue, reporting_period)
```

Fresh contexts prevent stale memoized values. For sensitivity analysis, retain the same model relationships and vary the actual controlling leaves. Restore baseline inputs when subsequent output should use them. Avoid import-time calculations that freeze adjustable values or external facts.

Use immutable domain types when distinguishing currencies, units, or sourced values matters. Define only meaningful operations, and give each unit type the same surface — if one currency supports `__add__` restricted to itself, the others do too, and each operator enforces its unit at runtime (`if not isinstance(other, USD): return NotImplemented`), since a shared field name lets a foreign unit slip through. A typed amount still needs a numeric surface: store the magnitude under a conventional field like `amount` or implement `__float__`, since reporting code and consumers coerce query answers with `float()`. Use typed `ops.map`/`map2` callbacks for rich answers; float-specialized `ops.add` is not a generic unit algebra. A currency conversion should explicitly demand the applicable FX input. Static type checking should reject invalid cross-unit operations, not silently erase the units.

For custom types, narrow `Maybe[T]` via `isna` or use `maybe.map_some` / `maybe.map2_some`. Use PEP 695 for generic functions, classes, and aliases. Supply precise `Series[K, V, W]` annotations where inference needs help; avoid `Any`, casts, or ignored diagnostics as substitutes for a correct contract.

For sourced inputs, parse the supplied data at an input leaf and retain the relevant citation fields with the source value (for example, an immutable dataclass or numeric subtype when numeric query compatibility is needed). Keep metadata reachable through ordinary access — direct attributes like `value.accn` or a plain `dict` under `value.citation`; a `MappingProxyType` or similar wrapper is neither an attribute bag nor a `dict` instance for downstream readers. A separate citation comment does not give a returned value metadata. Arithmetic may produce plain numbers, provided the derived graph retains a path to the sourced leaf. Test both the source metadata and the derived numeric behavior.

If data affects only a value, defer its load with `Thunk` when domain inspection must avoid I/O. If data defines period bounds or the domain, an effectful step or source rule can load it during structural discovery. Use supplied sources and the user's permitted access; financial formulas should not introduce unrelated fetching.
