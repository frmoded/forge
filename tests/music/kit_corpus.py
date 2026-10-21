"""Shared helpers for the Kit-view time-faithfulness tests (drain 2026-10-21-1930).

The Kit view (`kit_content`) is the single-staff fold of a percussion Score. This module holds what the tests and the frozen-fixture generator share:

  * the corpus: 13 named bars (`fixtures/kit_bars.json`, a copy of the client's provenance fixtures, which are the awkward bars the M3 inspector was verified on) and
    GENERATED bars (`fixtures/kit_generated_bars.json`: stored DATA, produced once by `fixtures/kit_frozen/generate.py` with a fixed seed, so the tests do not depend on a RNG);
  * `kit_xml_for(data)`: the PRODUCTION path — the same two calls the plugin makes (`rhythm_data_to_stream`, then `serialize_result`), not `to_kit_notation` in isolation;
  * `normalise(xml)`: music21 stamps fresh random ids on every export (part, score-part, instrument) and today's date; neither is content;
  * `kit_report(xml)` / `faithfulness_problems(data, xml)`: read the MusicXML the way a renderer does (a voice is laid end to end; <backup>/<forward> move the cursor; a <chord/> note
    shares its predecessor's onset) and compare every hit's ONSET with the data's, and every voice's LENGTH with the bar's.
"""
import json
import re
from fractions import Fraction
from pathlib import Path
from xml.etree import ElementTree as ET

HERE = Path(__file__).parent
FIXTURES = HERE / "fixtures"


def load_json(name):
  return json.loads((FIXTURES / name).read_text())


def named_bars():
  return load_json("kit_bars.json")


def generated_bars():
  return load_json("kit_generated_bars.json")


def all_bars():
  out = dict(named_bars())
  out.update(generated_bars())
  return out


def payload_for(data, title="kit"):
  """The production path: data -> Score -> serialized payload (the same two calls the plugin makes)."""
  from forge.music.lib import rhythm_data_to_stream
  from forge.core.serialization import serialize_result
  score = rhythm_data_to_stream(data)
  return serialize_result(score, {"snippet_id": title, "meta": {"title": title}})


def kit_xml_for(data, title="kit"):
  """The Kit MusicXML of the production payload, or None when the payload has none."""
  return payload_for(data, title).get("kit_content")


_RANDOM_IDS = [
  (re.compile(r'(id="P)[0-9a-f]{32}'), r'\1RANDOM'),
  (re.compile(r'(id="I)[0-9a-f]{32}'), r'\1RANDOM'),
  (re.compile(r"<encoding-date>[^<]*</encoding-date>"), "<encoding-date>DATE</encoding-date>"),
]


def normalise(xml):
  for rx, sub in _RANDOM_IDS:
    xml = rx.sub(sub, xml)
  return xml


def _position(note_el):
  step = note_el.findtext("unpitched/display-step")
  octave = note_el.findtext("unpitched/display-octave")
  if step is None:
    step = note_el.findtext("pitch/step")
    octave = note_el.findtext("pitch/octave")
  return f"{step}{octave}" if step else None


def kit_report(xml):
  """[{measure, divisions, voices: {voice_id: {end, notes: [(onset, position, notehead)]}}}]. `end` is the voice's cursor after its last element, `notes` are the NEW hits
  (a tied continuation is not a hit). Onsets and `end` are in divisions."""
  root = ET.fromstring(xml)
  out = []
  for part in root.findall("part"):
    for m in part.findall("measure"):
      divisions = 1
      voices = {}
      cursor = 0
      last_onset = 0
      for el in m:
        if el.tag == "attributes":
          d = el.findtext("divisions")
          if d:
            divisions = int(d)
        elif el.tag == "backup":
          cursor -= int(el.findtext("duration"))
        elif el.tag == "forward":
          cursor += int(el.findtext("duration"))
        elif el.tag == "note":
          v = el.findtext("voice") or "1"
          dur = int(el.findtext("duration") or 0)
          chord = el.find("chord") is not None
          onset = last_onset if chord else cursor
          rec = voices.setdefault(v, {"end": 0, "notes": []})
          if el.find("rest") is None:
            tie_stop = any(t.get("type") == "stop" for t in el.findall("tie"))
            if not tie_stop:
              nh = el.findtext("notehead") or "normal"
              rec["notes"].append((onset, _position(el), nh))
          if not chord:
            last_onset = onset
            cursor += dur
            rec["end"] = max(rec["end"], cursor)
      out.append({"measure": m.get("number"), "divisions": divisions, "voices": voices})
  return out


def bar_quarters(data):
  num, den = (int(x) for x in data["time_signature"].split("/"))
  return Fraction(num * 4, den)


def expected_positions():
  """channel -> kit display position, taken from the engine's own tables (so a change to the map is a change here too)."""
  from forge.music.lib import _RHYTHM_CHANNEL_INSTRUMENTS, _kit_lookup
  return {ch: _kit_lookup(factory())[0] for ch, factory in _RHYTHM_CHANNEL_INSTRUMENTS.items()}


def faithfulness_problems(data, xml):
  """Every problem a reader of this Kit MusicXML would hit: a voice whose length is not the bar's, a hit at the wrong time, a hit missing, a hit invented. [] = faithful."""
  problems = []
  rep = kit_report(xml)
  if len(rep) != 1:
    return [f"expected one measure, found {len(rep)}"]
  m = rep[0]
  bar = int(bar_quarters(data) * m["divisions"])
  for v, rec in m["voices"].items():
    if rec["end"] != bar:
      problems.append(f"voice {v} is {Fraction(rec['end'], m['divisions'])} quarters long in a {bar_quarters(data)}-quarter bar")
  pos = expected_positions()
  step_div = Fraction(bar, data["steps"])
  want = []
  for ch, cells in data["channels"].items():
    for i, c in enumerate(cells):
      if c is True or (isinstance(c, int) and not isinstance(c, bool) and c > 0):
        want.append((int(i * step_div), pos[ch]))
  got = [(o, p) for rec in m["voices"].values() for (o, p, _nh) in rec["notes"]]
  if sorted(want) != sorted(got):
    missing = sorted(set(want) - set(got))
    extra = sorted(set(got) - set(want))
    problems.append(f"hits differ from the data: missing {missing[:4]}{'...' if len(missing) > 4 else ''}, invented {extra[:4]}{'...' if len(extra) > 4 else ''}")
  return problems
