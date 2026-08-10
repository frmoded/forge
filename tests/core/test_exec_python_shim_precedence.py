"""Drain 2026-08-10-1700 — vault-note shims must shadow engine chips.

CCQA's Phase-4 cross-vault smoke (report 2026-08-10-1557) surfaced
this: music-theory's `Call [[rhythmic_line]]` resolved through the
mounted music-core NOTE at the registry layer, but the EXECUTED
binding was the engine's `forge.music.lib.rhythmic_line` chip
(signature `pattern`/`pitch`) — hence
`TypeError: ... unexpected keyword argument 'pitches'. Did you mean
'pitch'?`. Nothing was stale (all copies of the note carry the
current source; the prompt's H1-H5 all refuted): the bug is the
`local_ns` build in `exec_python`, which spread
`**_domain_globals_for(domains)` AFTER `**_build_snippet_shims(...)`,
so an engine chip silently overrode the same-named vault-note shim.

Documented precedence says the opposite: A4 shadowing ("a
hand-authored vault kick.md shadows the lib.py engine chip" — drain
1710's /generate dep-dedup comment) and the registry's resolution
order (authoring → imports → builtin LAST). This suite pins the
corrected namespace order: inputs > shims > domain globals > base.
"""

from forge.core.executor import exec_python
from forge.core.snippet_registry import SnippetRegistry
import forge.music.lib as _music_lib


def _registry_with_note(bare_id: str) -> SnippetRegistry:
  registry = SnippetRegistry()
  registry._vaults.setdefault("music-core", {})
  registry._vaults["music-core"][bare_id] = {
    "meta": {"type": "action"},
    "body": "",
    "path": f"/lib/music-core/{bare_id}.md",
    "vault": "music-core",
    "vault_path": "/lib/music-core",
    "source": "library",
    "snippet_id": f"music-core/{bare_id}",
  }
  return registry


CODE = """
def compute(context):
  return rhythmic_line
"""


def test_vault_note_shim_shadows_engine_chip():
  registry = _registry_with_note("rhythmic_line")
  stdout, result = exec_python(
    CODE, {}, registry=registry, snippet_id="t", domains=["music"],
  )
  # The binding must be the registry shim, NOT the engine chip.
  assert result is not _music_lib.rhythmic_line
  assert callable(result)


def test_engine_chip_still_injected_without_shadowing_note():
  registry = _registry_with_note("some_other_note")
  stdout, result = exec_python(
    CODE, {}, registry=registry, snippet_id="t", domains=["music"],
  )
  # No same-named vault note → the engine chip binds as before.
  assert result is _music_lib.rhythmic_line


def test_inputs_still_shadow_shims_and_chips():
  # Drain 1230's input-precedence contract survives the reorder:
  # inputs stay the outermost shadow.
  registry = _registry_with_note("rhythmic_line")
  stdout, result = exec_python(
    CODE, {"rhythmic_line": 42}, registry=registry, snippet_id="t",
    domains=["music"],
  )
  assert result == 42
