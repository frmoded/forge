import os
from pathlib import Path
from forge.core.snippet_registry import SnippetRegistry
from forge.core.graph_resolver import GraphResolver

VAULT = str(Path(__file__).parent.parent / "vault")


def test_scan_indexes_action_snippets():
  registry = SnippetRegistry()
  registry.scan(VAULT)
  snippet = registry.get("hello_forge")
  assert snippet is not None
  assert snippet["meta"]["type"] == "action"


def test_scan_uses_filename_as_id():
  registry = SnippetRegistry()
  registry.scan(VAULT)
  assert registry.get("hello_forge") is not None
  assert registry.get("greet") is not None
  assert registry.get("hello_world") is not None


def test_scan_populates_body():
  registry = SnippetRegistry()
  registry.scan(VAULT)
  snippet = registry.get("hello_forge")
  assert snippet["body"]


def test_scan_produces_no_errors_on_clean_vault():
  registry = SnippetRegistry()
  registry.scan(VAULT)
  assert registry.errors == []


def test_scan_skips_notes_without_type(tmp_path):
  (tmp_path / "untitled.md").write_text("---\n---\njust a note")
  registry = SnippetRegistry()
  registry.scan(str(tmp_path))
  assert registry.get("untitled") is None


def test_scan_reports_parse_errors(tmp_path):
  (tmp_path / "good.md").write_text("---\ntype: action\n---\n# Python\ncode")
  (tmp_path / "bad.md").write_text("---\ntype: action\n: broken: yaml:\n---\nbody")
  registry = SnippetRegistry()
  registry.scan(str(tmp_path))
  assert any("bad.md" in e for e in registry.errors)


def test_graph_resolver_finds_indexed_snippet():
  registry = SnippetRegistry()
  registry.scan(VAULT)
  resolver = GraphResolver(registry)
  assert resolver.resolve("hello_forge") is not None


def test_graph_resolver_returns_none_for_missing():
  registry = SnippetRegistry()
  registry.scan(VAULT)
  resolver = GraphResolver(registry)
  assert resolver.resolve("does_not_exist") is None
