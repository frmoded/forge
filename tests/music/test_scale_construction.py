"""scale_construction_exercise — grading + MCQ-shape + fixture parses.

CW-forge-music-lib-add-scale-construction-exercise-plus-first-fixtures
(drain 2026-08-05-1730). Written FAILING-FIRST: the primitive does not
exist yet.

Two step-1 findings shape these tests, and they are pinned here so the
constraints cannot drift silently:

1. The MCQ widget's parser (mcq-widget-core.ts) is STRICTER than the
   drain prompt's sketched outputs. CORRECT_RE is anchored at both
   ends — the ✓ branch must be a single line with nothing appended.
   Every ✗ branch must open with the exact diagnosis sentence
   `✗ Not quite. You picked '<X>'; the correct answer is '<Y>'.` or the
   card does not render. The regexes below MIRROR the TypeScript ones;
   if the plugin's parser changes shape, update both sides.

2. The piano widget serializes sharps-only, ascending (PC_NAMES has
   `A#`, never `Bb`; getSelection sorts by MIDI). So a correct F major
   attempt ARRIVES as `A#3` where the canonical spelling is `Bb3`.
   Sharp-for-flat is therefore accepted silently (the widget cannot do
   otherwise); spellings outside the widget's vocabulary (`Gb4`,
   `E#4` — only possible via typed input) are flagged as
   right-key-wrong-spelling.

The drain prompt's R1 audio tests are ABSENT by design: step 1 found no
engine-side render path (forge_render_music's fluidsynth+ffmpeg
pipeline lives on forge-transpile, unreachable from Pyodide), so this
drain ships text-only feedback per the prompt's own fallback plan.
"""
import json
import pathlib
import re

import pytest

from forge.music import lib
from forge.recipe import parser as recipe_parser


# Mirrors of mcq-widget-core.ts CORRECT_RE / WRONG_RE. Python's `$`
# would also match before a trailing newline, which JS's does not — so
# the correct-branch mirror uses \Z and the tests additionally assert
# single-line-ness.
CORRECT_RE = re.compile(r"^✓ Correct — (.+?)\.\Z")
WRONG_RE = re.compile(
  r"^✗ Not quite\. You picked (['\"])(.*?)\1; "
  r"the correct answer is (['\"])(.*?)\3\."
)

C_MAJOR = ["C4", "D4", "E4", "F4", "G4", "A4", "B4"]
A_MINOR = ["A3", "B3", "C4", "D4", "E4", "F4", "G4"]
G_MAJOR = ["G3", "A3", "B3", "C4", "D4", "E4", "F#4"]
# As the sharps-only piano widget serializes it (Bb3 arrives as A#3).
F_MAJOR_WIDGET = ["F3", "G3", "A3", "A#3", "C4", "D4", "E4"]


def grade(tonic, mode, pitches, **kw):
  return lib.scale_construction_exercise(tonic, mode, pitches, **kw)


# ------------------------------------------------------- happy path

def test_scale_construction_c_major_correct():
  assert grade("C4", "major", C_MAJOR) == "✓ Correct — C major scale."


def test_scale_construction_a_minor_correct():
  assert grade("A3", "minor", A_MINOR) == "✓ Correct — A minor scale."


def test_scale_construction_bare_tonic_defaults_to_octave_4():
  # Fixtures pass explicit octaves; a bare pitch-class still works.
  assert grade("C", "major", C_MAJOR) == "✓ Correct — C major scale."


# ------------------------------------------------------ wrong-order

def test_scale_construction_c_major_wrong_order():
  got = grade("C4", "major", list(reversed(C_MAJOR)))
  assert got.startswith("✗ Not quite.")
  assert "Right pitches, wrong order" in got


# ------------------------------------------------------- incomplete

def test_scale_construction_c_major_missing_note():
  got = grade("C4", "major", C_MAJOR[:6])
  assert "Incomplete — 6 of 7 notes" in got
  assert "B4" in got


def test_scale_construction_empty_attempt_is_incomplete():
  got = grade("C4", "major", [])
  assert "Incomplete — 0 of 7 notes" in got


# ----------------------------------------------------- wrong pitches

def test_scale_construction_c_major_extra_note():
  got = grade("C4", "major", C_MAJOR + ["C5"])
  assert got.startswith("✗ Not quite.")
  assert "C5" in got  # names the extra


def test_scale_construction_g_major_uses_fsharp():
  # F natural in G major is the classic transposition slip.
  wrong = G_MAJOR[:6] + ["F4"]
  got = grade("G3", "major", wrong)
  assert got.startswith("✗ Not quite.")
  assert "F#4" in got  # the expected list names the leading tone


def test_scale_construction_f_major_uses_bflat():
  # B natural in F major (should be Bb): a WRONG PITCH, not a
  # spelling issue — B3 and Bb3 are different keys.
  wrong = ["F3", "G3", "A3", "B3", "C4", "D4", "E4"]
  got = grade("F3", "major", wrong)
  assert got.startswith("✗ Not quite.")
  assert "Bb3" in got  # expected spelled with b, not music21's `-`


# ------------------------------------------------------- enharmonics

def test_scale_construction_widget_sharp_for_flat_is_correct():
  # The piano widget can ONLY emit A#3 for the Bb3 key. Flagging it
  # would fail every correct F major attempt made with the widget.
  assert grade("F3", "major", F_MAJOR_WIDGET) == "✓ Correct — F major scale."


def test_scale_construction_g_major_flags_wrong_spelling():
  # Gb4 for F#4: right key, but a spelling the widget never emits —
  # this can only be typed, and in G major the seventh is written F#.
  attempt = G_MAJOR[:6] + ["Gb4"]
  got = grade("G3", "major", attempt)
  assert got.startswith("✗ Not quite.")
  assert "wrong spelling" in got
  assert "F#4" in got


# ---------------------------------------------------- input coercion

def test_scale_construction_accepts_json_string_input():
  raw = json.dumps(C_MAJOR)
  assert grade("C4", "major", raw) == "✓ Correct — C major scale."


def test_scale_construction_accepts_list_input():
  assert grade("C4", "major", list(C_MAJOR)) == "✓ Correct — C major scale."


def test_scale_construction_accepts_comma_separated_input():
  assert grade("C4", "major", "C4, D4, E4, F4, G4, A4, B4") == (
    "✓ Correct — C major scale."
  )


# -------------------------------------------------------- bad inputs

def test_scale_construction_rejects_bad_tonic():
  with pytest.raises(ValueError, match="tonic"):
    grade("H2", "major", C_MAJOR)


def test_scale_construction_rejects_bad_mode():
  with pytest.raises(ValueError, match="mode"):
    grade("C4", "dorian", C_MAJOR)


def test_scale_construction_rejects_unparseable_student_pitch():
  with pytest.raises(ValueError, match="notaname"):
    grade("C4", "major", ["C4", "notaname"])


# ------------------------------------------- MCQ-widget parse contract

def test_scale_construction_output_matches_mcq_widget_parser():
  """Every branch must render as a card: ✓ single-line via CORRECT_RE,
  every ✗ via WRONG_RE with the diagnosis in the explanation slot."""
  outputs = {
    "correct": grade("C4", "major", C_MAJOR),
    "order": grade("C4", "major", list(reversed(C_MAJOR))),
    "incomplete": grade("C4", "major", C_MAJOR[:5]),
    "extra": grade("C4", "major", C_MAJOR + ["C5"]),
    "wrong": grade("F3", "major", ["F3", "G3", "A3", "B3", "C4", "D4", "E4"]),
    "spelling": grade("G3", "major", G_MAJOR[:6] + ["Gb4"]),
  }
  assert CORRECT_RE.match(outputs["correct"])
  assert "\n" not in outputs["correct"], "✓ branch must be single-line"
  for name in ("order", "incomplete", "extra", "wrong", "spelling"):
    assert WRONG_RE.match(outputs[name]), (
      f"{name} branch does not open with the exact MCQ diagnosis "
      f"sentence; the card will not render:\n{outputs[name]}"
    )
    assert "[[diatonic_scale]]" in outputs[name], (
      f"{name} branch should cite the chip that defines the answer"
    )


# ---------------------------------------------------- registration

def test_scale_construction_registration_lazy_list():
  from forge.core import executor
  assert "scale_construction_exercise" in executor._FORGE_MUSIC_LIB_NAMES
  assert "scale_construction_exercise" in executor._MUSIC_LAZY_CHIP_NAMES


# ------------------------------------------- fixture parses (I14)

VAULT = pathlib.Path(__file__).resolve().parents[3] / "forge-music"

FIXTURES = [
  "exercises/scale_construction_c_major_piano.md",
  "exercises/scale_construction_a_minor_piano.md",
  "exercises/scale_construction_g_major_piano.md",
  "exercises/scale_construction_f_major_piano.md",
]


@pytest.mark.parametrize("rel", FIXTURES)
def test_scale_fixture_recipe_parses(rel):
  path = VAULT / rel
  if not VAULT.exists():
    pytest.skip("forge-music not checked out beside forge")
  if rel.endswith("scale_construction_c_major_piano.md") and not path.exists():
    # Drain 2026-08-06-1600 finding: the wizard removed this fixture
    # from the live vault during the construct_c_major_piano
    # re-baseline (their Stream-with-TextExpression note supersedes
    # it). Loud skip, not a red: recreating it here would override a
    # wizard-lane authoring decision (L54). forge-core adjudicates
    # whether to drop it from FIXTURES for good.
    pytest.skip("c_major fixture removed by wizard re-baseline (drain 1600 FEEDBACK)")
  assert path.exists(), f"{rel} missing — drain 1730 ships four fixtures"
  body = path.read_text(encoding="utf-8")
  assert "# Recipe" in body, f"{rel} has no # Recipe facet"
  recipe = body.split("# Recipe", 1)[1].strip()
  try:
    recipe_parser.parse(recipe)
  except Exception as exc:  # I14: a parse failure is a drain failure
    pytest.fail(f"{rel} does not parse: {type(exc).__name__}: {exc}")


@pytest.mark.parametrize("rel", FIXTURES)
def test_scale_fixture_declares_piano_widget(rel):
  path = VAULT / rel
  if not path.exists():
    pytest.skip(f"{rel} not present")
  body = path.read_text(encoding="utf-8")
  assert "input_widgets:" in body
  assert "student_pitches: piano" in body


# ---- [2026-08-06-1600] audio_path opt-in (drain-1730 [R1] amendment) ----


class TestAudioPathOptIn:
  C_MAJOR = ["C4", "D4", "E4", "F4", "G4", "A4", "B4"]

  def test_correct_attempt_appends_audio_wikilink(self):
    out = lib.scale_construction_exercise(
      "C", "major", self.C_MAJOR,
      audio_path="ccqa-scratch/scale_attempts/c_major.mp3",
    )
    assert out.startswith("✓ Correct — C major scale.")
    assert out.endswith("\n\n[[ccqa-scratch/scale_attempts/c_major.mp3]]")

  def test_wrong_attempt_appends_audio_wikilink(self):
    out = lib.scale_construction_exercise(
      "C", "major", ["C4", "D4", "E4"], audio_path="a/b.mp3",
    )
    assert out.startswith("✗ Not quite.")
    assert "[[diatonic_scale]]" in out
    assert out.endswith("\n\n[[a/b.mp3]]")

  def test_audio_path_none_is_byte_identical_no_op(self):
    # No-op stays no-op: default call must not grow a trailing link.
    assert (
      lib.scale_construction_exercise("C", "major", self.C_MAJOR)
      == "✓ Correct — C major scale."
    )

  def test_blank_audio_path_treated_as_absent(self):
    assert (
      lib.scale_construction_exercise(
        "C", "major", self.C_MAJOR, audio_path="   ",
      )
      == "✓ Correct — C major scale."
    )

  def test_empty_attempt_gets_no_audio_link(self):
    # Nothing was played; nothing to hear.
    out = lib.scale_construction_exercise(
      "C", "major", [], audio_path="a/b.mp3",
    )
    assert "[[a/b.mp3]]" not in out

  def test_tempo_accepts_intable_and_rejects_junk(self):
    out = lib.scale_construction_exercise(
      "C", "major", self.C_MAJOR, audio_path="a/b.mp3", tempo="90",
    )
    assert out.endswith("[[a/b.mp3]]")
    with pytest.raises(ValueError, match="tempo"):
      lib.scale_construction_exercise(
        "C", "major", self.C_MAJOR, tempo="fast",
      )
