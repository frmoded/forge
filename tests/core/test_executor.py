import pytest
from forge.core.executor import extract_python, extract_section, exec_python, SnippetExecError


def test_extract_python_fenced():
  body = "# Python\n\n```python\nresult = 1\n```"
  assert extract_python(body) == "result = 1"


def test_extract_python_unfenced():
  body = "# Python\nresult = 1"
  assert extract_python(body) == "result = 1"


def test_extract_python_missing_heading():
  assert extract_python("no heading here") is None


def test_extract_python_stops_at_next_heading():
  body = "# Python\ncode = 1\n# Other\nother = 2"
  assert extract_python(body) == "code = 1"


def test_extract_section_plain_text():
  body = "# English\nhello world\n\n---\n\n# Python\ncode"
  assert extract_section(body, "english") == "hello world"


def test_extract_section_case_insensitive():
  body = "## ENGLISH\nhello\n# Python\ncode"
  assert extract_section(body, "english") == "hello"


def test_extract_section_missing():
  assert extract_section("no sections here", "english") is None


def test_exec_python_captures_stdout():
  stdout, _ = exec_python("print('hi')", {})
  assert stdout == "hi\n"


def test_exec_python_run_convention():
  code = "def run(context):\n  return 42"
  _, result = exec_python(code, {})
  assert result == 42


def test_exec_python_named_function_with_kwargs():
  code = "def greet(context, name):\n  return f'Hello {name}'"
  _, result = exec_python(code, {"name": "Alice"})
  assert result == "Hello Alice"


def test_exec_python_random_in_scope():
  code = "def run(context):\n  return random.randint(5, 5)"
  _, result = exec_python(code, {})
  assert result == 5


def test_exec_python_math_in_scope():
  code = "def run(context):\n  return math.floor(3.9)"
  _, result = exec_python(code, {})
  assert result == 3


def test_exec_python_blocks_import():
  with pytest.raises(SnippetExecError):
    exec_python("import os", {})


def test_exec_python_raises_snippet_exec_error_with_stdout():
  code = "print('before')\nraise ValueError('boom')"
  with pytest.raises(SnippetExecError) as exc_info:
    exec_python(code, {})
  assert "boom" in str(exc_info.value)
  assert "before" in exc_info.value.stdout
