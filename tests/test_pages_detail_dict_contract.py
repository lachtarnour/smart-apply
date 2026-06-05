"""Static contract test for Streamlit detail-dict consumers.

Streamlit pages execute as top-level scripts so they cannot be imported
in a regular pytest session. The pages still build small ad-hoc dicts
(``detail = {"title": job.title, ...}``) and then read fields out of
those dicts further down the file (``detail['title']``). When a new
consumer references a key that was never assigned, the bug only
surfaces at runtime — exactly the failure mode that produced the
``KeyError: 'job_id'`` regression in the Offres page after the manual
rescue feature was added.

This test parses each page file with the standard ``ast`` module and
ensures every ``detail['<key>']`` (or ``.get('<key>')``) read on a
``Name`` whose previous assignment is a dict literal is covered by a
key actually present in that dict literal. It runs in milliseconds and
needs no Streamlit runtime.

If a page legitimately reads keys that come from elsewhere (e.g. a
``detail.update(...)`` mid-flow), add the key to the ``_EXTRA_KEYS``
allowlist below or mark the assignment with the comment
``# detail-dict-contract: skip``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# Pages that build a ``detail`` dict and read from it.
_PAGES = (
    Path(__file__).resolve().parent.parent
    / "smartapply"
    / "app"
    / "pages"
    / "1_Offres.py",
)

# Per-file allowlist for keys that come from sources other than the
# nearest dict-literal assignment (loops, .update() calls, etc.).
_EXTRA_KEYS: dict[str, frozenset[str]] = {
    "1_Offres.py": frozenset(),
}


def _collect_dict_literal_keys(node: ast.Dict) -> set[str]:
    keys: set[str] = set()
    for k in node.keys:
        if isinstance(k, ast.Constant) and isinstance(k.value, str):
            keys.add(k.value)
    return keys


def _detail_dict_literal_keys(tree: ast.AST, var_name: str) -> set[str]:
    """Find the last top-level ``<var_name> = {...}`` assignment and
    return the dict literal's string keys."""
    keys: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id == var_name
                    and isinstance(node.value, ast.Dict)
                ):
                    # If multiple literal assignments exist, keep the
                    # union — pages that re-bind ``detail`` are rare and
                    # the union stays safely permissive.
                    keys |= _collect_dict_literal_keys(node.value)
    return keys


def _detail_subscript_keys(tree: ast.AST, var_name: str) -> set[str]:
    """All literal ``detail['x']`` subscript reads in the module."""
    keys: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == var_name
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        ):
            keys.add(node.slice.value)
        # Also catch ``detail.get('x')`` reads.
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == var_name
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            keys.add(node.args[0].value)
    return keys


@pytest.mark.parametrize("path", _PAGES, ids=lambda p: p.name)
def test_detail_dict_consumers_only_read_assigned_keys(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    assigned = _detail_dict_literal_keys(tree, "detail")
    consumed = _detail_subscript_keys(tree, "detail")
    allowlist = _EXTRA_KEYS.get(path.name, frozenset())
    missing = consumed - assigned - allowlist
    assert not missing, (
        f"{path.name} reads detail keys that are never assigned in the "
        f"dict literal: {sorted(missing)}. Add them to the literal or "
        f"update tests/test_pages_detail_dict_contract.py::_EXTRA_KEYS "
        f"if the source is intentional."
    )
