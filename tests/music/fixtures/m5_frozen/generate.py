"""Freeze the M5 no-harm digests from the PRE-CHANGE engine (drain 2026-10-22-1850).

  PYTHONPATH=<worktree of the commit BEFORE the change> python tests/music/fixtures/m5_frozen/generate.py <pre-change-sha>

Refuses unless `forge` resolves inside that worktree. Writes index.json next to this file."""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[3]))
from tests.music import m5_corpus as mc          # noqa: E402


def main(sha):
  import forge
  root = Path(os.environ["PYTHONPATH"].split(os.pathsep)[0]).resolve()
  if not str(Path(forge.__file__).resolve()).startswith(str(root)):
    sys.exit(f"refusing: forge is {forge.__file__}, not inside {root}")
  from forge.music.lib import extend_rhythm, rhythm_bars_to_stream
  from forge.core.serialization import serialize_result
  ser = lambda score, title: serialize_result(score, {"snippet_id": title, "meta": {"title": title}})
  cases = mc.case_digests(lambda s, b, st: extend_rhythm(s, bars=b, style=st), rhythm_bars_to_stream, ser)
  again = mc.case_digests(lambda s, b, st: extend_rhythm(s, bars=b, style=st), rhythm_bars_to_stream, ser)
  assert cases == again, "the pre-change export is not deterministic after normalising"
  vault = mc.clean_music_theory_head()
  notes = mc.note_digests(vault, ser)
  head = os.popen(f"git -C {mc.MT_VAULT} rev-parse HEAD").read().strip()
  (HERE / "index.json").write_text(json.dumps({"prefix_commit": sha, "music_theory_head": head, "cases": cases, "notes": notes}, indent=1, sort_keys=True))
  print(json.dumps({"cases": len(cases), "notes": len(notes)}))


if __name__ == "__main__":
  main(sys.argv[1])
