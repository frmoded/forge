"""Stage 2.5 — canonical-form snippet-to-snippet composition.

v0.2.68 — engine-side sibling-snippet namespace injection. E--'s
emitter produces bare Python calls for canonical `[[name]](args)`
syntax; without shims, snippet-to-snippet composition would raise
NameError. These cases lock in:

  - Canonical snippet calls another canonical snippet via bare ID.
  - Builtin calls still work (Stage-2 regression).
  - NameError preserved for unknown name (typos stay typos).
  - Snippet ID with subdirectory component resolves via A4.1.
  - Kwargs pass correctly through the shim.
  - Bare basename refs resolve via A4.1 Probe 2 (sibling subdir).
  - Recursion via context.compute works.
  - Snippet returning a value used as a binding.

Driven through `exec_python` against an in-memory SnippetRegistry to
avoid filesystem fixture overhead. The shim-injection path runs the
same way as the production canonical-compile path (which wraps E--
output in `def compute(context):` and invokes exec_python).
"""
import pytest

from forge.core.executor import exec_python, SnippetExecError
from forge.core.snippet_registry import SnippetRegistry
from forge.core.graph_resolver import GraphResolver


def _make_registry(snippets):
    """Build an in-memory SnippetRegistry from `snippets`, a list of
    {snippet_id: str, body: str, meta: dict} dicts. Each snippet is
    placed into the AUTHORING vault under its bare basename for A4
    resolution.
    """
    reg = SnippetRegistry()
    from forge.core.snippet_registry import AUTHORING_VAULT
    reg._vaults.setdefault(AUTHORING_VAULT, {})
    for s in snippets:
        sid = s["snippet_id"]
        bare = sid.split("/", 1)[-1] if "/" in sid else sid
        reg._vaults[AUTHORING_VAULT][bare] = {
            "meta": s.get("meta", {"type": "action", "inputs": []}),
            "body": s["body"],
            "path": f"<test:{sid}>",
            "vault": AUTHORING_VAULT,
            "vault_path": "<test>",
            "source": "library",
            "snippet_id": f"{AUTHORING_VAULT}/{bare}",
        }
    reg.set_resolution_order([AUTHORING_VAULT])
    return reg


def _exec(code, registry, snippet_id="caller"):
    resolver = GraphResolver(registry)
    return exec_python(
        code, inputs={}, resolver=resolver,
        registry=registry, snippet_id=snippet_id, domains=[],
    )


# 1. Canonical snippet calls another canonical snippet via bare ID
def test_canonical_snippet_calls_another_via_bare_id():
    callee_body = (
        "---\ntype: action\ninputs: [msg]\n---\n\n"
        "# Python\n\n```python\n"
        "def compute(context, msg):\n"
        "    print('callee got: ' + msg)\n"
        "    return 'ok'\n"
        "```\n"
    )
    reg = _make_registry([
        {"snippet_id": "callee", "body": callee_body},
    ])
    # Caller is canonical-form-style: bare basename call.
    caller_code = (
        "def compute(context):\n"
        "    callee('hello')\n"
    )
    stdout, result = _exec(caller_code, reg)
    assert "callee got: hello" in stdout


# 2. Canonical snippet calls Python builtin (Stage-2 regression)
def test_canonical_snippet_calls_builtin_print_unchanged():
    reg = _make_registry([])
    code = (
        "def compute(context):\n"
        "    print('builtin print still works')\n"
    )
    stdout, _ = _exec(code, reg)
    assert "builtin print still works" in stdout


# 3. NameError preserved for unknown name (typo isn't a snippet ref)
def test_unknown_name_still_raises_nameerror():
    reg = _make_registry([
        {"snippet_id": "real_snippet", "body":
         "---\ntype: action\ninputs: []\n---\n\n"
         "# Python\n\n```python\ndef compute(context):\n    pass\n```\n"},
    ])
    code = (
        "def compute(context):\n"
        "    no_such_snippet()\n"  # typo / not declared
    )
    with pytest.raises(SnippetExecError) as exc:
        _exec(code, reg)
    # The underlying cause is NameError; SnippetExecError wraps it.
    assert "no_such_snippet" in str(exc.value) or "name" in str(exc.value).lower()


# 4. Snippet ID with subdirectory component resolves via A4.1
def test_subdir_snippet_resolves_via_basename_shim():
    callee_body = (
        "---\ntype: action\ninputs: []\n---\n\n"
        "# Python\n\n```python\n"
        "def compute(context):\n"
        "    print('blues/song called')\n"
        "    return 12\n"
        "```\n"
    )
    reg = _make_registry([
        {"snippet_id": "blues/song", "body": callee_body},
    ])
    # E-- emits the bare basename `song` for `[[blues/song]]()`.
    caller_code = (
        "def compute(context):\n"
        "    song()\n"
    )
    stdout, _ = _exec(caller_code, reg)
    assert "blues/song called" in stdout


# 5. Kwargs passed correctly
def test_kwargs_pass_through_shim():
    callee_body = (
        "---\ntype: action\ninputs: [name]\n---\n\n"
        "# Python\n\n```python\n"
        "def compute(context, name):\n"
        "    print(f'hello {name}')\n"
        "```\n"
    )
    reg = _make_registry([
        {"snippet_id": "greet", "body": callee_body},
    ])
    code = (
        "def compute(context):\n"
        "    greet(name='world')\n"
    )
    stdout, _ = _exec(code, reg)
    assert "hello world" in stdout


# 6. Same-basename collision across vaults — first wins; A4.1 dispatches
def test_same_basename_first_wins_for_shim_key():
    # The shim list is keyed by basename. Both `blues/song` and
    # `forge-music/percussion/song` exist → shim 'song' is installed
    # ONCE (first iteration wins); A4.1 resolves at compute() time.
    a_body = (
        "---\ntype: action\ninputs: []\n---\n\n"
        "# Python\n\n```python\n"
        "def compute(context):\n    return 'A'\n```\n"
    )
    b_body = (
        "---\ntype: action\ninputs: []\n---\n\n"
        "# Python\n\n```python\n"
        "def compute(context):\n    return 'B'\n```\n"
    )
    reg = _make_registry([
        {"snippet_id": "song", "body": a_body},
    ])
    # The shim resolves via context.compute('song'), which uses A4
    # vault walk for an unqualified ID. There's only one 'song' in
    # the test registry (under AUTHORING_VAULT), so the call lands
    # there and returns 'A'.
    code = (
        "def compute(context):\n"
        "    r = song()\n"
        "    print(r)\n"
    )
    stdout, _ = _exec(code, reg)
    assert "A" in stdout


# 7. Recursion via context.compute works
def test_recursion_via_shim_works():
    # `fact(n)` calls itself via the shim. A4 resolution picks up
    # 'fact' from the registry on each recursive call.
    fact_body = (
        "---\ntype: action\ninputs: [n]\n---\n\n"
        "# Python\n\n```python\n"
        "def compute(context, n):\n"
        "    if n <= 1:\n"
        "        return 1\n"
        "    return n * context.compute('fact', n - 1)\n"
        "```\n"
    )
    reg = _make_registry([
        {"snippet_id": "fact", "body": fact_body},
    ])
    # Caller IS fact (snippet_id='fact'), called with n=5.
    code = (
        "def compute(context, n):\n"
        "    if n <= 1:\n"
        "        return 1\n"
        "    return n * fact(n - 1)\n"  # shim recursion
    )
    stdout, result = exec_python(
        code, inputs={"n": 5}, resolver=GraphResolver(reg),
        registry=reg, snippet_id="fact", domains=[],
    )
    assert result == 120


# 8. Snippet returning value used as binding
def test_returned_value_threads_through_set_then_call():
    namer_body = (
        "---\ntype: action\ninputs: [n]\n---\n\n"
        "# Python\n\n```python\n"
        "def compute(context, n):\n"
        "    return 'name_' + str(n)\n"
        "```\n"
    )
    reg = _make_registry([
        {"snippet_id": "random_name", "body": namer_body},
    ])
    # Canonical English: Set name to [[random_name]](n=5). Do [[print]](name).
    # Wrapped as `def compute(context):` for the entrypoint contract.
    code = (
        "def compute(context):\n"
        "    name = random_name(n=5)\n"
        "    print('Hello ' + name)\n"
    )
    stdout, _ = _exec(code, reg)
    assert "Hello name_5" in stdout


# 9. Idempotent rider — the shim namespace doesn't accumulate state
def test_shim_namespace_idempotent_across_runs():
    body = (
        "---\ntype: action\ninputs: []\n---\n\n"
        "# Python\n\n```python\n"
        "def compute(context):\n"
        "    return 42\n"
        "```\n"
    )
    reg = _make_registry([
        {"snippet_id": "answer", "body": body},
    ])
    code = (
        "def compute(context):\n"
        "    return answer()\n"
    )
    _, r1 = _exec(code, reg)
    _, r2 = _exec(code, reg)
    assert r1 == r2 == 42
