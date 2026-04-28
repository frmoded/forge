from pathlib import Path
import pytest
from forge.builtins.loader import load_builtin_vault
from forge.core.snippet_registry import parse_frontmatter

INSTALL_MD = """\
---
type: action
description: install a vault
---

# English

Install a vault from the registry.

# Python

```python
def run(context):
  return "ok"
```
"""

LOOKUP_MD = """\
---
type: action
inputs: [name]
description: registry lookup
---

# English

Look up a vault in the registry.

# Python

```python
def lookup(context, name):
  return name
```
"""

DATA_MD = """\
---
type: data
something: 42
---
"""

UNTYPED_MD = """\
---
title: notes
---
just a note, not a snippet
"""


def _write(path: Path, content: str) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(content)


def test_empty_directory_returns_empty_list(tmp_path):
  assert load_builtin_vault(tmp_path) == []


def test_missing_directory_returns_empty_list(tmp_path):
  assert load_builtin_vault(tmp_path / "does-not-exist") == []


def test_single_top_level_snippet(tmp_path):
  _write(tmp_path / "install.md", INSTALL_MD)
  result = load_builtin_vault(tmp_path)
  assert len(result) == 1
  s = result[0]
  assert s["snippet_id"] == "forge/install"
  assert s["vault"] == "forge"
  assert s["source"] == "builtin"
  assert s["meta"]["type"] == "action"


def test_nested_snippet_id_uses_slashes(tmp_path):
  _write(tmp_path / "registry" / "lookup.md", LOOKUP_MD)
  result = load_builtin_vault(tmp_path)
  assert len(result) == 1
  assert result[0]["snippet_id"] == "forge/registry/lookup"


def test_multiple_snippets(tmp_path):
  _write(tmp_path / "install.md", INSTALL_MD)
  _write(tmp_path / "registry" / "lookup.md", LOOKUP_MD)
  _write(tmp_path / "vault" / "extract.md", INSTALL_MD)
  result = load_builtin_vault(tmp_path)
  ids = sorted(s["snippet_id"] for s in result)
  assert ids == ["forge/install", "forge/registry/lookup", "forge/vault/extract"]


def test_skips_files_without_type(tmp_path):
  _write(tmp_path / "install.md", INSTALL_MD)
  _write(tmp_path / "untyped.md", UNTYPED_MD)
  result = load_builtin_vault(tmp_path)
  ids = [s["snippet_id"] for s in result]
  assert "forge/install" in ids
  assert "forge/untyped" not in ids


def test_data_snippets_are_loaded(tmp_path):
  _write(tmp_path / "config.md", DATA_MD)
  result = load_builtin_vault(tmp_path)
  assert len(result) == 1
  assert result[0]["meta"]["type"] == "data"
  assert result[0]["meta"]["something"] == 42


def test_uses_existing_parser(tmp_path):
  """Snippets loaded by the loader match what the existing parser produces."""
  _write(tmp_path / "install.md", INSTALL_MD)
  result = load_builtin_vault(tmp_path)
  expected_meta, expected_body = parse_frontmatter(INSTALL_MD)
  assert result[0]["meta"] == expected_meta
  assert result[0]["body"] == expected_body


def test_parse_error_propagates(tmp_path):
  """Malformed builtins must fail loud — they're vendored, not user content."""
  _write(tmp_path / "broken.md", "---\n: bad: yaml: [unclosed\n---\nbody")
  with pytest.raises(Exception):
    load_builtin_vault(tmp_path)


def test_path_field_set(tmp_path):
  _write(tmp_path / "install.md", INSTALL_MD)
  result = load_builtin_vault(tmp_path)
  assert result[0]["path"].endswith("install.md")


def test_real_builtins_directory_loadable():
  """The real forge/builtins/snippets/ directory must always be loadable, even when empty."""
  result = load_builtin_vault()
  assert isinstance(result, list)
