#!/usr/bin/env python3
"""Print a compact Markdown snapshot of the importable Orcaset API."""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import inspect
from collections.abc import Iterable
from types import ModuleType
from typing import Any


MODULES = ("orcaset", "orcaset.span", "orcaset.point", "orcaset.cell", "orcaset.stmt")
CORE_NAMES = (
    "Context",
    "Formula",
    "Period",
    "Span",
    "Point",
    "SpanSeries",
    "PointSeries",
    "SpanSeriesFamily",
    "PointSeriesFamily",
    "Stmt",
    "Group",
    "Total",
)


def package_version(package_name: str) -> str:
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        module = importlib.import_module(package_name)
        version = getattr(module, "__version__", "unknown")
        return str(version)


def public_names(module: ModuleType) -> list[str]:
    explicit = getattr(module, "__all__", None)
    if explicit is not None:
        return sorted(str(name) for name in explicit)
    return sorted(name for name in vars(module) if not name.startswith("_"))


def safe_signature(obj: Any) -> str:
    try:
        return str(inspect.signature(obj))
    except Exception:
        return ""


def iter_public_callables(module: ModuleType) -> Iterable[tuple[str, Any]]:
    for name in public_names(module):
        obj = getattr(module, name, None)
        if inspect.isfunction(obj) and getattr(obj, "__module__", None) == module.__name__:
            yield name, obj


def print_class_detail(name: str, cls: type[Any]) -> None:
    print(f"### `{name}`")
    signature = safe_signature(cls)
    if signature:
        print(f"- constructor: `{name}{signature}`")

    members: list[str] = []
    for member_name, member in inspect.getmembers(cls):
        if member_name.startswith("_"):
            continue
        if inspect.isfunction(member) or inspect.ismethoddescriptor(member):
            member_signature = safe_signature(member)
            members.append(f"- `{member_name}{member_signature}`")

    for line in members:
        print(line)
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", default="orcaset", help="Top-level package to inspect")
    args = parser.parse_args()

    version = package_version(args.package)
    root = importlib.import_module(args.package)

    print(f"# Orcaset API Snapshot: {version}")
    print()
    print(f"- package: `{args.package}`")
    print(f"- module path: `{getattr(root, '__file__', 'unknown')}`")
    print()

    print("## Top-Level Exports")
    for name in public_names(root):
        print(f"- `{name}`")
    print()

    print("## Core Classes")
    for name in CORE_NAMES:
        obj = getattr(root, name, None)
        if inspect.isclass(obj):
            print_class_detail(name, obj)

    print("## Module Callables")
    for module_name in MODULES[1:]:
        module = importlib.import_module(module_name)
        print(f"### `{module_name}`")
        for name, obj in iter_public_callables(module):
            if inspect.isclass(obj) and obj.__module__ == module_name:
                continue
            signature = safe_signature(obj)
            if signature:
                print(f"- `{name}{signature}`")
            else:
                print(f"- `{name}`")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
