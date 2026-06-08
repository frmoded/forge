"""v0.2.81 Item A — tests for detect_facet_form_strip_trap.

The Obsidian YAML-strip trap: a snippet's frontmatter has english_hash
(the cache-write artefact from a prior canonical compute) but no
longer has facet_form: canonical — Obsidian silently stripped it on a
prior write. The engine then routes through the legacy `else: return
code` path and uses the cached `# Python` directly, silently ignoring
fresh English-facet edits the user expects to invalidate the cache.

The pure-decision helper returns True only when the trap is detected.
Caller (pyodide-host.ts `_forge_run_snippet`) consults it + emits a
deduped console.warn to surface the trap to power users.

NOTE on naming: the v0.2.81 prompt phrased this as "has slot_resolutions
but facet_form is absent" — slot_resolutions is not actually a
frontmatter field (it's a transient parameter on resolve_action_code).
The detection signal we use is english_hash (the real cache-write
artefact that `writePythonAndEnglishHash` persists). Functionally
equivalent: both mark "this snippet was previously cached as canonical."
"""
from forge.core.executor import detect_facet_form_strip_trap


def test_trap_fires_when_slot_resolutions_present_and_no_facet_form():
  """The canonical trap shape: Obsidian stripped facet_form silently."""
  meta = {"english_hash": "abc123"}
  assert detect_facet_form_strip_trap(meta) is True


def test_trap_fires_when_slot_resolutions_present_and_facet_form_not_canonical():
  """Even if facet_form is set to some non-canonical value (e.g. 'free')
  alongside slot_resolutions, the cache contract is broken — surface."""
  meta = {
    "english_hash": "abc123",
    "facet_form": "free",
  }
  assert detect_facet_form_strip_trap(meta) is True


def test_trap_does_not_fire_when_facet_form_canonical():
  """Healthy state — both fields present, cache contract intact."""
  meta = {
    "english_hash": "abc123",
    "facet_form": "canonical",
  }
  assert detect_facet_form_strip_trap(meta) is False


def test_trap_does_not_fire_when_no_slot_resolutions():
  """No slot_resolutions → no trap risk. Free-English snippets, slot-
  free canonical snippets, fresh snippets all land here."""
  meta = {"type": "action"}
  assert detect_facet_form_strip_trap(meta) is False


def test_trap_does_not_fire_when_english_hash_is_empty_string():
  """Empty english_hash is functionally equivalent to absent — no
  cache-write artefact, no canonical-history signal."""
  meta = {
    "english_hash": "",
    "facet_form": "free",
  }
  assert detect_facet_form_strip_trap(meta) is False


def test_trap_does_not_fire_on_fresh_free_english_snippet():
  """A free-English snippet with type: action + no english_hash + no
  facet_form is the legacy default; nothing to warn about."""
  meta = {"type": "action", "inputs": []}
  assert detect_facet_form_strip_trap(meta) is False


def test_trap_does_not_fire_on_none_meta():
  """Defensive — caller passing None must not crash."""
  assert detect_facet_form_strip_trap(None) is False


def test_trap_does_not_fire_on_empty_meta():
  """Defensive — caller passing {} must not crash."""
  assert detect_facet_form_strip_trap({}) is False
