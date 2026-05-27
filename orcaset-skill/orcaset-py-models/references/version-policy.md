# Orcaset Skill Version Policy

Check the Orcaset version used by the user's project against the available reference versions in `references/api-<version>.md`.

Ignore patch-version differences. For example, use `api-0.2.0.md` for `0.2.1` unless local API inspection shows a relevant difference.

If there is a minor or major version difference:

1. Compare the installed Orcaset API against the closest available API reference in `references/`.
2. Use `scripts/inspect_orcaset_api.py` when a compact installed-API summary would help.
3. Tell the user about the minor or major version difference.
4. Ask whether they want to update this skill by pulling the most recent version from [github.com/orcaset/orcaset-py/orcaset-skill](https://github.com/orcaset/orcaset-py/tree/main/orcaset-skill) and reinstalling it.
