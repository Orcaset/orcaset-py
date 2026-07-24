# Agent instructions

## Linting and type checking

- Use **ruff** for linting and formatting. Run `ruff` over any modified Python files before finishing.
- Use **pyrefly** for type checking. All new and modified Python code must pass `pyrefly check` with no issues.
- Examples under `examples/` each have their own `pyrefly.toml`. Run `pyrefly check` from inside the relevant example directory when checking example code.

## Typing rules (strict)

- Do **not** use `typing.cast` / `cast(...)`.
- Do **not** use `# type: ignore`, `# pyrefly: ignore`, or any other comment or config that suppresses type errors.
- Do **not** weaken types to silence the checker (for example by introducing `Any` solely to avoid errors).
- Fix the underlying types or design until `pyrefly check` is clean.
