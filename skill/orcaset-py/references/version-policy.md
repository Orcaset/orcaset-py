# Orcaset Skill Version Policy

Check the Orcaset version used by the user's project against the available reference versions in `references/api-<version>.md`.

Ignore patch-version differences. For example, use `api-0.2.x.md` for `0.2.1` if `api-0.2.1.md` is not available.

If there is a minor or major version difference:

1. Warn the user that this skill version does not match the library version.
2. Ask whether they want to update this skill by pulling the most recent version from [github.com/orcaset/orcaset-py/orcaset-skill](https://github.com/orcaset/orcaset-py/tree/main/orcaset-skill) and reinstalling it.
3. If a compatible version does not exist on GitHub or the user does not want to update this skill, do your best based on the information in this skill and inspection of the installed library version.
