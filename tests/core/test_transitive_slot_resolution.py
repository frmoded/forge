"""Drain 2026-08-10-1830 — transitive `{{ }}` slot resolution.

CCQA's Phase-4 cross-vault batch smoke (report 2026-08-10-1615,
Smoke 1) hit a SlotCacheMissError calling music-core's rhythmic_line
(now pitched_line, drain 1810) transitively via
`Call [[rhythmic_line]] with pitches=..., rhythm_pattern=...` from a
music-theory note — TWICE: the first-pass miss correctly triggered
the plugin's two-pass /resolve-slot protocol, but the SECOND pass
(with slot_resolutions populated) failed IDENTICALLY ("slot
resolution second pass failed").

Source trace (verified, not inherited per I16): `ForgeContext.compute`
(executor.py:505) — used for EVERY `context.compute(...)` dispatch,
which is how `Call [[name]] with ...` / bare shim calls resolve a
callee — calls `resolve_action_code(snippet)` with NO
`slot_resolutions` argument (executor.py:524, pre-fix), and its
recursive `exec_python(...)` call for the callee's own body also
omits `slot_resolutions` (executor.py:531-540, pre-fix). This is
TRUE REGARDLESS OF VAULT: `slot_resolutions` was only ever threaded
into the TOP-LEVEL snippet's own resolve_action_code call
(`_forge_run_snippet` in pyodide-host.ts); any snippet reached via
`context.compute()` — the composition primitive for EVERY
`Call [[x]]` — never received it, so a callee with unresolved
`{{ }}` slots misses on every pass, forever. Cross-vault mounting
(drain 1430) merely supplied the first snippet with `{{ }}` slots
ever invoked transitively; CCQA's same-vault "control" run succeeded
only because it Forge-clicked the note directly (top-level), not
transitively.
"""

import pytest

from forge.core.executor import exec_python
from forge.core.snippet_registry import SnippetRegistry, AUTHORING_VAULT
from forge.core.graph_resolver import GraphResolver
from forge.core.slot_cache import compute_slot_cache_key


V2_CALLEE_BODY = """---
type: action
inputs:
  - x
---

# Description

Add one.

# Recipe

Return {{ x + 1 }}.
"""

V2_CALLER_BODY = """---
type: action
---

# Description

Call the slotted callee.

# Recipe

Return Call [[callee]] with x=3.
"""


@pytest.fixture()
def registry_with_v2_slotted_callee():
  registry = SnippetRegistry()
  registry._vaults[AUTHORING_VAULT] = {
    "caller": {
      "meta": {"type": "action"},
      "body": V2_CALLER_BODY,
      "path": "/lib/authoring/caller.md",
      "vault": AUTHORING_VAULT,
      "vault_path": "/lib/authoring",
      "source": "authoring",
      "snippet_id": "caller",
    },
    "callee": {
      "meta": {"type": "action", "inputs": ["x"]},
      "body": V2_CALLEE_BODY,
      "path": "/lib/authoring/callee.md",
      "vault": AUTHORING_VAULT,
      "vault_path": "/lib/authoring",
      "source": "authoring",
      "snippet_id": "callee",
    },
  }
  registry.set_resolution_order([AUTHORING_VAULT])
  return registry


def test_transitive_v2_call_first_pass_raises_with_callee_slot_cache_miss_payload(
  registry_with_v2_slotted_callee,
):
  """First pass, cold cache, transitive Call [[callee]] with a `{{ }}`
  slot: the callee's resolve_action_code raises SlotCacheMissError
  naming the CALLEE's snippet_id, but — because that raise happens
  INSIDE the caller's own exec_python try/except (via
  context.compute) — the generic `except Exception as e: raise
  SnippetExecError(str(e)) from e` handler catches + rewraps it.
  Confirmed AS PRODUCTION BEHAVIOR (not itself the bug to fix): the
  JSON payload survives str(e) verbatim, and the plugin's
  `_maybeExtractSlotCacheMiss` (server.ts) is deliberately
  class-name-agnostic — it scans any error message for a `{...}`
  blob with a `slot_cache_miss` key — so this wrapping is already
  tolerated end-to-end. Matches CCQA's exact observed shape (3-entry
  missing list keyed to music-core/rhythmic_line, not the top-level
  caller, wrapped in a SnippetExecError whose message is the JSON)."""
  from forge.core.executor import SnippetExecError
  from forge.recipe import extract_recipe_body, parse, transpile
  import json

  registry = registry_with_v2_slotted_callee
  resolver = GraphResolver(registry)
  caller_code = transpile(parse(extract_recipe_body(V2_CALLER_BODY)))

  with pytest.raises(SnippetExecError) as exc_info:
    exec_python(caller_code, {}, resolver, registry=registry, snippet_id="caller")
  payload = json.loads(str(exc_info.value))
  missing = payload["slot_cache_miss"]
  assert len(missing) == 1
  assert missing[0]["snippet_id"] == "callee"
  assert "x + 1" in missing[0]["slot_text"]


def test_transitive_v2_call_second_pass_with_resolutions_succeeds(
  registry_with_v2_slotted_callee,
):
  """THE BUG (pre-fix): even with slot_resolutions correctly keyed to
  the CALLEE's snippet_id (exactly what the plugin's handleSlotCacheMiss
  builds from /resolve-slot's response), passing it to exec_python for
  the TOP-LEVEL caller must resolve the TRANSITIVE callee's slot too.
  Pre-fix this raises the SAME SlotCacheMissError again (infinite
  miss); post-fix it succeeds."""
  from forge.recipe import extract_recipe_body, parse, transpile

  registry = registry_with_v2_slotted_callee
  resolver = GraphResolver(registry)
  caller_code = transpile(parse(extract_recipe_body(V2_CALLER_BODY)))

  cache_key = compute_slot_cache_key("x + 1", "callee")
  slot_resolutions = {cache_key: "x + 1"}

  stdout, result = exec_python(
    caller_code, {}, resolver, registry=registry, snippet_id="caller",
    slot_resolutions=slot_resolutions,
  )
  assert result == 4


def test_three_level_transitive_chain_propagates_resolutions(
  registry_with_v2_slotted_callee,
):
  """Depth check: the SAME slot_resolutions dict must survive an
  additional hop (caller -> middle -> callee), confirming the fix
  threads through context.compute's recursive exec_python call, not
  just the first level."""
  registry = registry_with_v2_slotted_callee
  registry._vaults[AUTHORING_VAULT]["middle"] = {
    "meta": {"type": "action"},
    "body": (
      "---\ntype: action\n---\n\n# Description\n\nRelay.\n\n"
      "# Recipe\n\nReturn Call [[callee]] with x=3.\n"
    ),
    "path": "/lib/authoring/middle.md",
    "vault": AUTHORING_VAULT,
    "vault_path": "/lib/authoring",
    "source": "authoring",
    "snippet_id": "middle",
  }
  registry._vaults[AUTHORING_VAULT]["caller"]["body"] = (
    "---\ntype: action\n---\n\n# Description\n\nRelay twice.\n\n"
    "# Recipe\n\nReturn Call [[middle]].\n"
  )
  resolver = GraphResolver(registry)
  from forge.recipe import extract_recipe_body, parse, transpile

  caller_code = transpile(parse(extract_recipe_body(
    registry._vaults[AUTHORING_VAULT]["caller"]["body"])))
  cache_key = compute_slot_cache_key("x + 1", "callee")
  slot_resolutions = {cache_key: "x + 1"}

  stdout, result = exec_python(
    caller_code, {}, resolver, registry=registry, snippet_id="caller",
    slot_resolutions=slot_resolutions,
  )
  assert result == 4
