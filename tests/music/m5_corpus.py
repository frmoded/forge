"""Shared helpers for the M5 no-harm proof (drain 2026-10-22-1850): per-bar tempo in `rhythm_bars_to_stream` and `extend_rhythm(..., tempo_change_pct=0)` must change NOTHING for
what already worked. The corpus is every 4/4 16-step seed of the kit corpus (`fixtures/kit_bars.json`) x the three extend styles x 1, 4 and 8 bars, plus the three music-theory
`rhythm_extended_*` notes run from a CLEAN `git archive` of that vault's HEAD. For each case this records sha256 digests of: the extend_rhythm result as JSON, and the serialized
payload of `rhythm_bars_to_stream` (multi-staff MusicXML and Kit MusicXML, normalised for music21's random ids and date, and the MIDI base64). `fixtures/m5_frozen/generate.py`
freezes them from the PRE-CHANGE engine (a worktree of the commit before the change), never from the code under test."""
import hashlib
import json
import os
import subprocess
import tempfile

from tests.music import kit_corpus as kc

STYLES = ("repeat_with_fills", "building", "ghost_notes")
BAR_COUNTS = (1, 4, 8)
NOTES = ("rhythm_extended_fills", "rhythm_extended_building", "rhythm_extended_ghost")
MT_VAULT = os.path.expanduser("~/projects/music-theory")


def seeds():
  return {n: d for n, d in kc.named_bars().items() if d["time_signature"] == "4/4" and d["steps"] == 16 and d["group_size"] == 4}


def _sha(text):
  return hashlib.sha256(text.encode()).hexdigest()


def digests_for_payload(payload):
  return {
    "multi_staff": _sha(kc.normalise(payload["multi_staff_content"])),
    "kit": _sha(kc.normalise(payload["kit_content"])) if payload.get("kit_content") else None,
    "midi": _sha(payload.get("multi_staff_midi_base64") or ""),
  }


def case_digests(extend, to_stream, serialize):
  """{case id: digests}. `extend(seed, bars, style)`, `to_stream(bars_list)` and `serialize(score, title)` are the engine's three calls (passed in so the generator can use the pre-change code)."""
  out = {}
  for name, seed in seeds().items():
    for style in STYLES:
      for bars in BAR_COUNTS:
        cid = f"{name}/{style}/{bars}"
        built = extend(seed, bars, style)
        out[cid] = {"extend_json": _sha(json.dumps(built, sort_keys=True)), **digests_for_payload(serialize(to_stream(built), cid))}
  return out


def note_digests(vault_dir, serialize):
  from forge.core.executor import exec_python, resolve_action_code
  from forge.core.registry import GraphResolver, SnippetRegistry
  reg = SnippetRegistry(); reg.scan(vault_dir); res = GraphResolver(reg)
  out = {}
  for n in NOTES:
    snip = res.resolve(n)
    code = resolve_action_code(snip)
    _, result = exec_python(code, {}, res, args=(), vault_path=vault_dir, registry=reg, snippet_id=snip["snippet_id"], domains=["music"])
    out[f"note/{n}"] = digests_for_payload(serialize(result, n))
  return out


def clean_music_theory_head(rev="HEAD"):
  """A temp dir holding `git archive <rev>` of music-theory: the committed notes only (the working tree carries untracked same-named litter that makes the registry refuse)."""
  d = tempfile.mkdtemp(prefix="m5-mt-")
  arc = subprocess.run(["git", "-C", MT_VAULT, "archive", rev], capture_output=True, check=True).stdout
  subprocess.run(["tar", "-x", "-C", d], input=arc, check=True)
  return d
