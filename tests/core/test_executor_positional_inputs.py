"""v0.2.77 — positional foot-gun fix.

When a canonical snippet has declared inputs (`inputs: [n]`) and is
invoked positionally (`[[double]](5)`), the engine MUST bind the
positional args to the declared input names in order before exec'ing
the snippet body. Pre-v0.2.77, _takes_only_context short-circuited
to fn(context), dropping args silently; the body's reference to `n`
then raised NameError — opaque + unhelpful to first-week learners.

v0.2.77 fix: when _takes_only_context(fn) is True AND args is
non-empty, look up declared_inputs from the snippet meta and bind
positional → declared by index. If declared_inputs is missing or
shorter than args, raise a clear ValueError with the snippet id,
declared inputs, and the correct keyword call form.
"""
import pytest
from forge.core.executor import exec_python, SnippetExecError


# Canonical wrap (mirrors the transpile in resolve_action_code:570-576).
CANONICAL_DOUBLE = (
  "def compute(context):\n"
  "    return n * 2\n"
)
CANONICAL_NO_INPUTS = (
  "def compute(context):\n"
  "    return 42\n"
)
# Free-English shape — explicit input params in compute signature.
FREE_ENGLISH_DOUBLE = (
  "def compute(context, n):\n"
  "    return n * 2\n"
)


def test_canonical_snippet_with_declared_inputs_accepts_positional_call():
  """`[[double]](5)` against canonical `inputs: [n]` should bind 5 to n
  and return 10 (not raise NameError)."""
  _, result = exec_python(
    CANONICAL_DOUBLE, inputs={}, args=(5,),
    snippet_id="forge-tutorial/double",
    declared_inputs=["n"],
  )
  assert result == 10


def test_canonical_snippet_keyword_call_unchanged():
  """`[[double]](n=5)` keeps working (regression check)."""
  _, result = exec_python(
    CANONICAL_DOUBLE, inputs={"n": 5}, args=(),
    snippet_id="forge-tutorial/double",
    declared_inputs=["n"],
  )
  assert result == 10


def test_canonical_snippet_with_two_declared_inputs_accepts_positional():
  """Multi-input canonical: `[[add]](3, 4)` against `inputs: [a, b]`."""
  code = (
    "def compute(context):\n"
    "    return a + b\n"
  )
  _, result = exec_python(
    code, inputs={}, args=(3, 4),
    snippet_id="forge-tutorial/add",
    declared_inputs=["a", "b"],
  )
  assert result == 7


def test_canonical_snippet_mixed_positional_and_keyword():
  """`[[add]](3, b=4)` should bind 3 to a, 4 to b (Python-style)."""
  code = (
    "def compute(context):\n"
    "    return a + b\n"
  )
  _, result = exec_python(
    code, inputs={"b": 4}, args=(3,),
    snippet_id="forge-tutorial/add",
    declared_inputs=["a", "b"],
  )
  assert result == 7


def test_canonical_snippet_with_too_many_positional_args_raises_clear_error():
  """`[[double]](5, 99)` against `inputs: [n]` raises a clear error
  citing the snippet's declared inputs + correct call form."""
  # v0.2.77 — positional-binding ValueError is raised before the
  # snippet body runs; the existing executor catch wraps non-
  # SnippetExecError exceptions into SnippetExecError. The message
  # content (which the user actually reads) is what matters.
  with pytest.raises(SnippetExecError) as exc:
    exec_python(
      CANONICAL_DOUBLE, inputs={}, args=(5, 99),
      snippet_id="forge-tutorial/double",
      declared_inputs=["n"],
    )
  msg = str(exc.value)
  assert "forge-tutorial/double" in msg, f"missing snippet id in error: {msg}"
  assert "inputs ['n']" in msg or "inputs [n]" in msg, \
    f"missing inputs list in error: {msg}"
  assert "2 args" in msg, f"missing arg count in error: {msg}"
  assert "[[" in msg and "n=" in msg, \
    f"missing correct call form in error: {msg}"


def test_canonical_snippet_no_inputs_positional_call_raises_clear_error():
  """`[[no_args]](5)` against `inputs: []` raises a clear error
  ("snippet takes no inputs")."""
  with pytest.raises(SnippetExecError) as exc:
    exec_python(
      CANONICAL_NO_INPUTS, inputs={}, args=(5,),
      snippet_id="forge-tutorial/no_args",
      declared_inputs=[],
    )
  msg = str(exc.value)
  assert "forge-tutorial/no_args" in msg, f"missing snippet id: {msg}"
  assert "no inputs" in msg, f"missing 'no inputs' phrase: {msg}"
  assert "1 args" in msg, f"missing arg count: {msg}"


def test_legacy_free_english_snippet_positional_unchanged():
  """Free-English snippets have explicit def compute(context, n, m, ...).
  _takes_only_context returns False for these; positional routing via
  fn(context, *args) is Python-native and stays working."""
  _, result = exec_python(
    FREE_ENGLISH_DOUBLE, inputs={}, args=(5,),
    snippet_id="forge-tutorial/double_free",
    declared_inputs=["n"],
  )
  assert result == 10


def test_no_declared_inputs_param_back_compat():
  """Existing callers that don't pass declared_inputs keep working
  (the v0.2.77 fix is gated on declared_inputs being provided)."""
  _, result = exec_python(
    CANONICAL_DOUBLE, inputs={"n": 5}, args=(),
    snippet_id="forge-tutorial/double",
  )
  assert result == 10
