"""Generator for the Kit-view fixtures (drain 2026-10-21-1930). NOT run by the test suite; the suite reads what this wrote.

  python tests/music/fixtures/kit_frozen/generate.py data
      writes ../kit_generated_bars.json: GENERATED bar DATA from a fixed seed (the tests read the stored data, so they do not depend on the RNG).

  PYTHONPATH=<checkout of the PRE-FIX commit> python tests/music/fixtures/kit_frozen/generate.py freeze <pre-fix-sha>
      writes index.json (per bar: sha256 of the normalised Kit XML as the PRE-FIX engine made it, and whether that XML was faithful) and the full XML of the named bars.
      It refuses to run unless `forge` resolves INSIDE that checkout: a frozen fixture must come from the pre-fix code, never from a copy the fixed code wrote.
"""
import hashlib
import json
import os
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[3]))          # tests/ is a package (tests.music.kit_corpus); the engine comes from PYTHONPATH
from tests.music import kit_corpus as kc          # noqa: E402

CHANNELS = ["kick", "snare", "hihat", "bell", "claves", "conga_high", "conga_low"]
SHAPES = [("4/4", 16, 4), ("4/4", 8, 2), ("3/4", 12, 4), ("6/8", 12, 2), ("2/4", 8, 4), ("5/4", 20, 4)]


def generate_data(n=120, seed=20261021):
  rng = random.Random(seed)
  out = {}
  for i in range(n):
    ts, steps, group = rng.choice(SHAPES)
    k = rng.randint(1, 7)
    chans = rng.sample(CHANNELS, k)
    density = rng.choice([0.1, 0.2, 0.35, 0.5, 0.8])
    channels = {}
    for ch in chans:
      cells = []
      for _ in range(steps):
        if rng.random() < density:
          cells.append(rng.choice([True, True, True, rng.randint(40, 127)]))
        else:
          cells.append(False)
      channels[ch] = cells
    out[f"gen_{i:03d}"] = {"time_signature": ts, "steps": steps, "group_size": group, "swing_pct": 0, "tempo_bpm": rng.choice([70, 81, 100, 120]), "channels": channels}
  return out


def freeze(sha):
  import forge
  root = Path(os.environ["PYTHONPATH"].split(os.pathsep)[0]).resolve()
  if not str(Path(forge.__file__).resolve()).startswith(str(root)):
    sys.exit(f"refusing: forge is {forge.__file__}, not inside {root}")
  index = {"prefix_commit": sha, "bars": {}}
  for name, data in kc.all_bars().items():
    payload = kc.payload_for(data, name)
    xml = payload["kit_content"]
    norm = kc.normalise(xml)
    index["bars"][name] = {
      "sha256": hashlib.sha256(norm.encode()).hexdigest(),
      "faithful_prefix": kc.faithfulness_problems(data, xml) == [],
      # the parts of the payload this fix must NOT touch (drain 1930 §4: multi-staff view, MIDI)
      "multi_staff_sha256": hashlib.sha256(kc.normalise(payload["multi_staff_content"]).encode()).hexdigest(),
      "midi_sha256": hashlib.sha256((payload.get("multi_staff_midi_base64") or "").encode()).hexdigest(),
    }
    if name in kc.named_bars():
      (HERE / f"{name}.xml").write_text(norm)
  # determinism: a second run must produce the same normalised bytes, or the comparison would be meaningless
  for name, data in list(kc.all_bars().items())[:20]:
    assert hashlib.sha256(kc.normalise(kc.kit_xml_for(data, name)).encode()).hexdigest() == index["bars"][name]["sha256"], f"{name}: the pre-fix export is not deterministic after normalising"
  (HERE / "index.json").write_text(json.dumps(index, indent=1, sort_keys=True))
  print(json.dumps({"bars": len(index["bars"]), "faithful_prefix": sum(b["faithful_prefix"] for b in index["bars"].values())}))


if __name__ == "__main__":
  mode = sys.argv[1]
  if mode == "data":
    (HERE.parent / "kit_generated_bars.json").write_text(json.dumps(generate_data(), indent=1))
    print("wrote kit_generated_bars.json")
  elif mode == "freeze":
    freeze(sys.argv[2])
  else:
    sys.exit(__doc__)
