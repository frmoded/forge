"""Smoke test for music21 as a backend dependency.

Confirms (1) music21 is installed in the Forge backend env, (2) a snippet's
Python facet can import and use it through the existing runtime path, and
(3) results from inside the runtime match results from a direct import.

Per docs/tech-debt.md ("Per-vault Python dependencies"), music21 lives at
the backend level for now; this test is the boundary check that keeps
that arrangement honest.
"""

from forge.core.executor import exec_python


_SNIPPET_BODY = """
def compute(context):
  from music21 import note
  n = note.Note("D4")
  return {"name": n.name, "octave": n.octave, "midi": n.pitch.midi}
"""


def test_snippet_can_import_music21_through_runtime():
  _, result = exec_python(_SNIPPET_BODY, {}, trusted=True)
  assert result == {"name": "D", "octave": 4, "midi": 62}


def test_runtime_matches_direct_music21_baseline():
  """The snippet must produce identical output to a plain `from music21 import note`."""
  from music21 import note
  n = note.Note("D4")
  expected = {"name": n.name, "octave": n.octave, "midi": n.pitch.midi}

  _, result = exec_python(_SNIPPET_BODY, {}, trusted=True)
  assert result == expected


def test_music21_chord_through_runtime():
  """Exercise a slightly richer surface so a future music21 break is caught here."""
  body = """
def compute(context):
  from music21 import chord
  c = chord.Chord(["C4", "E4", "G4"])
  return {
    "pitched_names": [p.nameWithOctave for p in c.pitches],
    "is_major_triad": c.isMajorTriad(),
    "root_name": c.root().name,
  }
"""
  _, result = exec_python(body, {}, trusted=True)
  assert result["pitched_names"] == ["C4", "E4", "G4"]
  assert result["is_major_triad"] is True
  assert result["root_name"] == "C"
