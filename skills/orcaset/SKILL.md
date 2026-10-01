---
name: orcaset
description: Build and modify financial statement models in Python with Orcaset. Use when the model uses Orcaset, builds financial models in Python, or the user requests it.
license: Complete terms in LICENSE.txt
---

# Financial modeling with Orcaset

Orcaset models are lazy dependency graphs of date- or period-keyed line items. Dependencies are resolved using effect handlers, and all dependencies are traced within an evaluation context.

Use this skill as your guide to the library. Read library source only to confirm specific signatures or behavior.

## Process

1. **Examine environment** Confirm whether the environment has the `orcaset` Python library installed and its version. If `orcaset` is not installed, notify the user and try to install it from PyPI. Also confirm whether the environment has a type checker (prefer `pyrefly`) and code formatter such as `ruff`. Check for `numpy-financial` and other installed libraries.
2. **Review patterns** Read [core.md](references/core.md) and any applicable additional reference files before any actions involving writing, reading, or modifying any code.
3. **Build.** After considering any model intricacies, write the code. For schedules such as cohorts, depreciation, debt, or linked statements, read [patterns.md](references/patterns.md). If inputs need units, citations, or other metadata, read [values.md](references/values.md).
4. **Verify** Verify model and code structure according to [verification.md](references/verification.md). Run `scripts/check.sh` which confirms type checking with pyrefly and formats code with ruff until it passes.
5. **Produce outputs** Run or report final outputs to the user.

## References

| File | Read when |
|---|---|
| [core.md](references/core.md) | Every task: core workflow, periods and dates, queries, line-item design |
| [patterns.md](references/patterns.md) | Building cohorts, depreciation, debt, rollforwards, or three-statement models |
| [output.md](references/output.md) | Structuring or formatting statements and exported results |
| [verification.md](references/verification.md) | Required checks before reporting any model results |
| [values.md](references/values.md) | Inputs that carry units, citations, or other metadata |
