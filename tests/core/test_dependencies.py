"""Phase 1 tests for static dependency extraction (B7)."""
from forge.core.dependencies import (
  extract_dependencies,
  apply_dependencies_to_body,
)


def test_no_calls_returns_empty():
  assert extract_dependencies("def compute(context):\n  return 42") == []


def test_single_literal_call():
  src = (
    "def compute(context):\n"
    "  v = context.compute('alpha')\n"
    "  return v\n"
  )
  assert extract_dependencies(src) == ["alpha"]


def test_multiple_distinct_calls_in_source_order():
  src = (
    "def compute(context):\n"
    "  a = context.compute('alpha')\n"
    "  b = context.compute('beta')\n"
    "  c = context.compute('gamma')\n"
    "  return [a, b, c]\n"
  )
  assert extract_dependencies(src) == ["alpha", "beta", "gamma"]


def test_repeated_calls_deduplicated():
  src = (
    "def compute(context):\n"
    "  a = context.compute('alpha')\n"
    "  b = context.compute('beta')\n"
    "  c = context.compute('alpha')\n"
    "  return [a, b, c]\n"
  )
  assert extract_dependencies(src) == ["alpha", "beta"]


def test_dynamic_dispatch_ignored():
  src = (
    "def compute(context):\n"
    "  for name in ['x', 'y']:\n"
    "    context.compute(name)\n"
    "    context.compute(f'snippet_{name}')\n"
    "  return None\n"
  )
  assert extract_dependencies(src) == []


def test_kwargs_and_positional_args_ignored():
  """Args after the first don't affect dependency detection."""
  src = (
    "def compute(context):\n"
    "  return context.compute('greet', 'Alice', name='Bob')\n"
  )
  assert extract_dependencies(src) == ["greet"]


def test_malformed_python_returns_empty():
  assert extract_dependencies("def compute(context: ::") == []


def test_non_context_compute_ignored():
  src = (
    "def compute(context):\n"
    "  other.compute('x')\n"
    "  ctx.compute('y')\n"
    "  return None\n"
  )
  assert extract_dependencies(src) == []


def test_nested_calls_extracted():
  src = (
    "def compute(context):\n"
    "  return context.compute('outer', x=context.compute('inner'))\n"
  )
  # Both should be extracted; inner appears second in source by lineno+col.
  deps = extract_dependencies(src)
  assert set(deps) == {"outer", "inner"}


# --- apply_dependencies_to_body ---

def test_apply_appends_section_when_absent():
  body = "# English\n\ntext\n\n# Python\n\n```python\nx = 1\n```\n"
  out = apply_dependencies_to_body(body, ["alpha", "beta"])
  assert "# Dependencies" in out
  assert "[[alpha]] [[beta]]" in out
  # Section appears AFTER python.
  assert out.index("# Python") < out.index("# Dependencies")


def test_apply_replaces_existing_section():
  body = (
    "# English\n\ntext\n\n# Python\n\n```python\nx=1\n```\n\n"
    "# Dependencies\n\n*Synced from Python.*\n\n[[old]]\n"
  )
  out = apply_dependencies_to_body(body, ["new"])
  # Only one Dependencies header — no duplication.
  assert out.count("# Dependencies") == 1
  assert "[[new]]" in out
  assert "[[old]]" not in out


def test_apply_empty_deps_removes_section():
  body = (
    "# English\n\ntext\n\n# Python\n\n```python\nx=1\n```\n\n"
    "# Dependencies\n\n*note*\n\n[[old]]\n"
  )
  out = apply_dependencies_to_body(body, [])
  assert "# Dependencies" not in out
  assert "[[old]]" not in out
  # Body's other content survives.
  assert "# English" in out
  assert "# Python" in out


def test_apply_idempotent():
  body = "# English\n\ntext\n\n# Python\n\n```python\nx=1\n```\n"
  once = apply_dependencies_to_body(body, ["a", "b"])
  twice = apply_dependencies_to_body(once, ["a", "b"])
  assert once == twice


def test_apply_subheadings_inside_deps_not_terminators():
  """Subheadings (## Sub) shouldn't terminate the section, since the section
  is system-managed and won't contain them. But if anything weird sneaks in,
  we still terminate at the next *top-level* heading."""
  body = (
    "# English\n\n# Python\n\n```python\nx=1\n```\n\n"
    "# Dependencies\n\n*note*\n\n[[old]]\n## Subheading\nstuff\n"
  )
  out = apply_dependencies_to_body(body, ["new"])
  # Subheading and 'stuff' are part of the deps section in this implementation
  # and get stripped along with everything else.
  assert "[[new]]" in out
  assert "[[old]]" not in out
