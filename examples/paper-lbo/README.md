# Paper LBO

Simple LBO model from Wharton. The goal of this example is to highlight model comparisons to the Excel implementation in a simple format.

Follows the case study at [LBO Practice Model](https://careerservices.upenn.edu/resources/lbo-practice-model/).

## Reference

[`reference/wharton-lbo-practice-model.xlsx`](reference/wharton-lbo-practice-model.xlsx) — Wharton Career Services LBO practice workbook (blank model, answer key, and notes). Source: [careerservices.upenn.edu](https://careerservices.upenn.edu/resources/lbo-practice-model/).

## Highlights

* **Circularity:** Enabled by passing `seed` and a `distance` function to at least one accessor function that cuts the cycle. No circuit breaker required — orcaset can't get stuck in the same way.
* **Concise:** Significantly more concise than the Python script for building the Excel version.
* **Sensitivity:** Sensitize variables by making them rules set to different values in different contexts.

## Run

This is a standalone uv project with its own library dependencies. orcaset is pinned to `0.8.0` and resolved from the repo checkout.

Requires Python 3.14+.

```sh
cd examples/paper-lbo
uv run python main.py
```
