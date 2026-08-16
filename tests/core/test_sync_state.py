"""Tests for forge.core.sync_state — the shared sync-state derivation.

Drain 2026-08-16-2000 (Phase 1 of the Option C `sync_state` retirement,
`forge-moda-bootstrap/sync-state-ownership-options.md`).

Shape: NEW-FEATURE per cc-prompt-queue.md §"Test discipline for
NEW-FEATURE prompts" — tests before done, failing-first not meaningful
against a module that does not exist yet (module-not-found validates
nothing). The real non-vacuity evidence is §"The four incidents"
below: for every note where the PERSISTED field lied or vanished, the
derivation is asserted to produce a DIFFERENT and TRUE value. That is
the claim this whole phase rests on, so it is asserted, not narrated.

Fixture provenance (per I21 — fixtures cite their source, never a
prompt sketch):
  - murmuration          `forge-client-obsidian/assets/vaults/music-theory/percussion/murmuration.md`
  - solitary             `forge-client-obsidian/assets/vaults/music-core/percussion_lab/solitary.md`
  - scale_quality_quiz   `forge-client-obsidian/assets/vaults/music-theory/exercises/scale_quality_quiz.md`
                         (pre-backfill) + the post-backfill shape recorded verbatim in
                         `forge-moda-bootstrap/test-reports/2026-08-16-0940-obsidian-regression.md` step 12
  - step-5 post-run      the frontmatter block pasted in that same report, step 5
Each hash below is copied from the cited file/report, not invented.
"""

import hashlib

import pytest

from forge.core.sync_state import (
  EMPTY_FACET_HASH,
  STALE_PYTHON,
  STALE_RECIPE,
  SYNC_STATES,
  SYNCED,
  UNKNOWN,
  derive_sync_state,
)

# Readable stand-ins for "some non-empty facet body's hash". Distinct
# values so a mixed-up comparison cannot pass by coincidence.
D = "d" * 64
R = "r" * 64
P = "p" * 64
OTHER = "0" * 64


# ---------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------


def test_the_vocabulary_is_exactly_four_distinct_values():
  """Non-vacuity: the four values must not collapse into aliases, and
  the module must not quietly grow a fifth."""
  assert len(set(SYNC_STATES)) == 4
  assert set(SYNC_STATES) == {SYNCED, STALE_RECIPE, STALE_PYTHON, UNKNOWN}


def test_stale_both_is_NOT_in_the_vocabulary():
  """Drain §4 — a writer value with no consumer is flagged for
  retirement, not ported. `stale-both` is the plugin's only value with
  zero readers, and under first-broken-link semantics it is subsumed by
  `stale-recipe` anyway."""
  assert "stale-both" not in SYNC_STATES


def test_empty_facet_hash_is_the_sha256_of_the_empty_string():
  """Both the plugin's normalizer and forge-mcp's map "" and None to
  the same value; nothing else in this module may drift from it."""
  assert EMPTY_FACET_HASH == hashlib.sha256(b"").hexdigest()
  assert EMPTY_FACET_HASH == (
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  )


# ---------------------------------------------------------------------
# Full vocabulary coverage — one aligned lineage per outcome
# ---------------------------------------------------------------------


def test_both_links_current_is_synced():
  assert derive_sync_state({
    "description_hash": D, "recipe_hash": R, "python_hash": P,
    "recipe_derived_from_description_hash": D,
    "python_derived_from_recipe_hash": R,
    "source_facet": "description",
  }) == SYNCED


def test_recipe_lineage_pointing_at_an_old_description_is_stale_recipe():
  assert derive_sync_state({
    "description_hash": D, "recipe_hash": R, "python_hash": P,
    "recipe_derived_from_description_hash": OTHER,
    "python_derived_from_recipe_hash": R,
    "source_facet": "description",
  }) == STALE_RECIPE


def test_python_lineage_pointing_at_an_old_recipe_is_stale_python():
  assert derive_sync_state({
    "description_hash": D, "recipe_hash": R, "python_hash": P,
    "recipe_derived_from_description_hash": D,
    "python_derived_from_recipe_hash": OTHER,
    "source_facet": "description",
  }) == STALE_PYTHON


def test_no_hash_stamps_at_all_is_unknown():
  assert derive_sync_state({"type": "action"}) == UNKNOWN


def test_every_vocabulary_value_is_reachable():
  """Non-vacuity: a value nothing can produce is dead vocabulary."""
  produced = {
    derive_sync_state({
      "description_hash": D, "recipe_hash": R, "python_hash": P,
      "recipe_derived_from_description_hash": D,
      "python_derived_from_recipe_hash": R,
    }),
    derive_sync_state({
      "description_hash": D, "recipe_hash": R, "python_hash": P,
      "recipe_derived_from_description_hash": OTHER,
      "python_derived_from_recipe_hash": R,
    }),
    derive_sync_state({
      "description_hash": D, "recipe_hash": R, "python_hash": P,
      "recipe_derived_from_description_hash": D,
      "python_derived_from_recipe_hash": OTHER,
    }),
    derive_sync_state({}),
  }
  assert produced == set(SYNC_STATES)


def test_result_is_always_a_member_of_the_vocabulary():
  """Degenerate inputs map to defined values, never to exceptions
  (drain §4). Anything the YAML parser can hand us must land in the
  enum."""
  hostile = [
    {},
    {"description_hash": None, "recipe_hash": None, "python_hash": None},
    {"description_hash": 12, "recipe_hash": [], "python_hash": {}},
    {"source_facet": "banana", "description_hash": D},
    {"source_facet": None, "recipe_hash": R},
    {"description_hash": D, "recipe_hash": R, "python_hash": P,
     "recipe_derived_from_description_hash": True,
     "python_derived_from_recipe_hash": 0},
  ]
  for fm in hostile:
    assert derive_sync_state(fm) in SYNC_STATES, fm


# ---------------------------------------------------------------------
# First-broken-link ordering
# ---------------------------------------------------------------------


def test_both_links_broken_reports_the_upstream_one():
  """The value names the FIRST broken link in D -> R -> P; everything
  downstream of it is implicitly out of date. This is why `stale-both`
  is redundant rather than missing."""
  assert derive_sync_state({
    "description_hash": D, "recipe_hash": R, "python_hash": P,
    "recipe_derived_from_description_hash": OTHER,
    "python_derived_from_recipe_hash": OTHER,
    "source_facet": "description",
  }) == STALE_RECIPE


# ---------------------------------------------------------------------
# source_facet gating — an ignored upstream facet is not a stale one
# ---------------------------------------------------------------------


def test_recipe_as_source_makes_the_description_link_irrelevant():
  """Constitution S9: upstream of the source renders `— ignored`, not
  `— out of date`. A hand-authored Recipe has no lineage to Description
  and that is not staleness."""
  assert derive_sync_state({
    "description_hash": D, "recipe_hash": R, "python_hash": P,
    "recipe_derived_from_description_hash": OTHER,
    "python_derived_from_recipe_hash": R,
    "source_facet": "recipe",
  }) == SYNCED


def test_recipe_as_source_still_evaluates_the_python_link():
  assert derive_sync_state({
    "description_hash": D, "recipe_hash": R, "python_hash": P,
    "python_derived_from_recipe_hash": OTHER,
    "source_facet": "recipe",
  }) == STALE_PYTHON


def test_python_as_source_has_nothing_downstream_to_be_stale():
  assert derive_sync_state({
    "description_hash": D, "recipe_hash": R, "python_hash": P,
    "recipe_derived_from_description_hash": OTHER,
    "python_derived_from_recipe_hash": OTHER,
    "source_facet": "python",
  }) == SYNCED


def test_source_facet_synced_evaluates_both_links():
  """`synced` is a legitimate stored `source_facet` value (the plugin's
  VALID_SOURCE_VALUES). It must not short-circuit the evaluation."""
  assert derive_sync_state({
    "description_hash": D, "recipe_hash": R, "python_hash": P,
    "recipe_derived_from_description_hash": OTHER,
    "python_derived_from_recipe_hash": R,
    "source_facet": "synced",
  }) == STALE_RECIPE


def test_an_unrecognized_source_facet_evaluates_both_links():
  """Conservative: garbage in the field must never buy a `synced`."""
  assert derive_sync_state({
    "description_hash": D, "recipe_hash": R, "python_hash": P,
    "recipe_derived_from_description_hash": OTHER,
    "python_derived_from_recipe_hash": R,
    "source_facet": "banana",
  }) == STALE_RECIPE


# ---------------------------------------------------------------------
# Degenerate: absent facets, absent lineage, partial lineage
# ---------------------------------------------------------------------


def test_a_recipe_that_was_never_produced_is_stale_recipe():
  """Description has content, Recipe is empty. forge-mcp's own note
  shell reasons exactly this way: "Recipe is empty and therefore not
  derived from this Description. `stale-recipe` is the honest opening
  state." (vault_fs.py:1131)"""
  assert derive_sync_state({
    "description_hash": D,
    "recipe_hash": EMPTY_FACET_HASH,
    "python_hash": EMPTY_FACET_HASH,
    "source_facet": "description",
  }) == STALE_RECIPE


def test_a_python_that_was_never_produced_is_stale_python():
  assert derive_sync_state({
    "description_hash": D, "recipe_hash": R,
    "python_hash": EMPTY_FACET_HASH,
    "recipe_derived_from_description_hash": D,
    "source_facet": "description",
  }) == STALE_PYTHON


def test_absent_lineage_on_a_present_facet_is_stale_not_synced():
  """I18 — hash-value consistency does not imply a derivation happened.
  A Recipe with no `recipe_derived_from_*` stamp was never certified as
  derived; absent-of-lineage may not be read as `synced`."""
  assert derive_sync_state({
    "description_hash": D, "recipe_hash": R, "python_hash": P,
    "python_derived_from_recipe_hash": R,
    "source_facet": "description",
  }) == STALE_RECIPE


def test_an_empty_description_leaves_nothing_for_the_recipe_to_derive_from():
  """Vacuous link, not a broken one — an empty parent cannot be the
  source of drift."""
  assert derive_sync_state({
    "description_hash": EMPTY_FACET_HASH,
    "recipe_hash": R, "python_hash": P,
    "python_derived_from_recipe_hash": R,
    "source_facet": "recipe",
  }) == SYNCED


def test_partial_lineage_with_an_unstampable_parent_is_unknown():
  """`description_hash` absent entirely (not empty — ABSENT) means the
  Description-to-Recipe link cannot be evaluated. Reporting `synced`
  off an unevaluable link is the exact failure this phase exists to
  end."""
  assert derive_sync_state({
    "recipe_hash": R, "python_hash": P,
    "python_derived_from_recipe_hash": R,
  }) == UNKNOWN


def test_a_definite_stale_outranks_an_unevaluable_link():
  """Knowing one link is broken is more useful than reporting the
  note-wide `unknown` its unstamped sibling would produce."""
  assert derive_sync_state({
    "recipe_hash": R, "python_hash": P,
    "python_derived_from_recipe_hash": OTHER,
  }) == STALE_PYTHON


def test_a_note_whose_facets_are_all_empty_has_nothing_to_be_stale():
  assert derive_sync_state({
    "description_hash": EMPTY_FACET_HASH,
    "recipe_hash": EMPTY_FACET_HASH,
    "python_hash": EMPTY_FACET_HASH,
  }) == SYNCED


def test_hashes_absent_but_source_facet_python_is_still_unknown():
  """The all-absent guard runs BEFORE the source_facet short-circuit —
  a legacy note may not buy `synced` with one field."""
  assert derive_sync_state({"source_facet": "python"}) == UNKNOWN


# ---------------------------------------------------------------------
# Legacy `*_derived_from_source_hash` field names
# ---------------------------------------------------------------------


def test_legacy_recipe_derived_from_source_hash_is_read_as_a_fallback():
  """Live notes carry both names (murmuration, solitary) and the v11.4
  backfill stamps ONLY the legacy one. Both hold the DESCRIPTION hash,
  so the fallback is sound for the Recipe link."""
  assert derive_sync_state({
    "description_hash": D, "recipe_hash": R, "python_hash": P,
    "recipe_derived_from_source_hash": D,
    "python_derived_from_recipe_hash": R,
    "source_facet": "description",
  }) == SYNCED


def test_the_modern_recipe_lineage_field_wins_over_the_legacy_twin():
  assert derive_sync_state({
    "description_hash": D, "recipe_hash": R, "python_hash": P,
    "recipe_derived_from_description_hash": OTHER,
    "recipe_derived_from_source_hash": D,
    "python_derived_from_recipe_hash": R,
    "source_facet": "description",
  }) == STALE_RECIPE


def test_legacy_python_derived_from_source_hash_is_NOT_a_fallback():
  """It holds the DESCRIPTION hash, not the Recipe hash — verified in
  murmuration (`python_derived_from_source_hash` == `description_hash`
  == 8aaecfa4..., while `python_derived_from_recipe_hash` == 788c6cce..
  == `recipe_hash`). Treating it as a fallback would compare Python's
  lineage against the wrong parent and manufacture a false `synced`."""
  assert derive_sync_state({
    "description_hash": D, "recipe_hash": R, "python_hash": P,
    "recipe_derived_from_description_hash": D,
    "python_derived_from_source_hash": D,
    "source_facet": "description",
  }) == STALE_PYTHON


# ---------------------------------------------------------------------
# The four incidents — the persisted field lied; the derivation must not
# ---------------------------------------------------------------------

# 1. murmuration (drain 1710 false-stale). Lineage is fully aligned;
#    the persisted field says stale.
MURMURATION = {
  "type": "action",
  "description_hash": "8aaecfa415bb7256066f21225870611353cd418387b45e6b1dd258eb4f996af3",
  "recipe_hash": "788c6cce4d86865b1313053e5e7dcd3dd11139f080b9ba86a1adc1476c257df8",
  "python_hash": "4dbc6dd03755d44539a0328354ccdb1973e3127e17f0ee52e1503aea7cebfbb8",
  "recipe_derived_from_source_hash": "8aaecfa415bb7256066f21225870611353cd418387b45e6b1dd258eb4f996af3",
  "python_derived_from_source_hash": "8aaecfa415bb7256066f21225870611353cd418387b45e6b1dd258eb4f996af3",
  "source_facet": "description",
  "recipe_derived_from_description_hash": "8aaecfa415bb7256066f21225870611353cd418387b45e6b1dd258eb4f996af3",
  "python_derived_from_recipe_hash": "788c6cce4d86865b1313053e5e7dcd3dd11139f080b9ba86a1adc1476c257df8",
  "recipe_version": 5,
  "sync_state": "stale-recipe",
}

# 2. percussion_lab/solitary (drain 1800). Recipe IS current; the
#    Python facet was never produced (python_hash is the empty hash).
SOLITARY = {
  "type": "action",
  "inputs": ["bars"],
  "source_facet": "description",
  "sync_state": "stale-recipe",
  "description_hash": "ff4f50ccd1a7dc0477b0fa9a22bca658f89d18bf5c30c02c9192f7f4b87ac137",
  "recipe_hash": "33e0149c82c810a5313da479fb3abd6982e6d422a41f2e6c0220137cc65a89d2",
  "python_hash": EMPTY_FACET_HASH,
  "recipe_derived_from_description_hash": "ff4f50ccd1a7dc0477b0fa9a22bca658f89d18bf5c30c02c9192f7f4b87ac137",
  "recipe_derived_from_source_hash": "ff4f50ccd1a7dc0477b0fa9a22bca658f89d18bf5c30c02c9192f7f4b87ac137",
  "python_derived_from_recipe_hash": EMPTY_FACET_HASH,
  "python_derived_from_source_hash": "ff4f50ccd1a7dc0477b0fa9a22bca658f89d18bf5c30c02c9192f7f4b87ac137",
  "recipe_version": 2,
}

# 3a. scale_quality_quiz as it sits on disk before any backfill: a
#     `synced` claim with not one hash to support it.
QUIZ_PRE_BACKFILL = {
  "type": "action",
  "inputs": ["guess"],
  "input_enums": {"guess": ["major", "minor", "diminished", "augmented"]},
  "sync_state": "synced",
}

# 3b. the same note the moment it is OPENED: the v11.4 backfill writes a
#     stub `def compute(context): return None`, stamps three hashes and
#     ONE derived-from field (the legacy recipe one, per the panel log),
#     and sets `sync_state: synced`.
QUIZ_POST_BACKFILL = {
  "type": "action",
  "description_hash": D,
  "recipe_hash": R,
  "python_hash": P,  # the manufactured stub's hash
  "recipe_derived_from_source_hash": D,
  "sync_state": "synced",
}

# 4. the step-5 post-run note: every hash and both lineage fields
#    present and aligned — and no `sync_state` field at all.
STEP5_POST_RUN = {
  "type": "action",
  "description_hash": "f492eeba3db3ae9924a20d5f3c670a1d8b56983cbfd6c91eae7f4149b0acc684",
  "recipe_hash": "dcdee86b473f8b8222f55ab9959444837980b67bdb5eaef48277b7b62ea148a6",
  "python_hash": "f27d0b1b851839a42dc761273fea81f5bdeac679c7ec8d4036c2977610fe1867",
  "recipe_derived_from_source_hash": "f492eeba3db3ae9924a20d5f3c670a1d8b56983cbfd6c91eae7f4149b0acc684",
  "source_facet": "recipe",
  "recipe_derived_from_description_hash": "f492eeba3db3ae9924a20d5f3c670a1d8b56983cbfd6c91eae7f4149b0acc684",
  "python_derived_from_source_hash": "f492eeba3db3ae9924a20d5f3c670a1d8b56983cbfd6c91eae7f4149b0acc684",
  "python_derived_from_recipe_hash": "dcdee86b473f8b8222f55ab9959444837980b67bdb5eaef48277b7b62ea148a6",
}


def test_incident_1_murmuration_derives_synced_where_the_field_said_stale():
  assert derive_sync_state(MURMURATION) == SYNCED
  assert MURMURATION["sync_state"] == "stale-recipe"


def test_incident_2_solitary_names_the_link_that_is_actually_broken():
  """The persisted value blames the Recipe. The Recipe is current; the
  Python facet is the one that was never produced."""
  assert derive_sync_state(SOLITARY) == STALE_PYTHON
  assert SOLITARY["sync_state"] == "stale-recipe"


def test_incident_3a_quiz_pre_backfill_refuses_to_certify_synced():
  assert derive_sync_state(QUIZ_PRE_BACKFILL) == UNKNOWN
  assert QUIZ_PRE_BACKFILL["sync_state"] == "synced"


def test_incident_3b_a_manufactured_stub_is_not_a_derivation():
  """I18 in one assertion: the backfill wrote the Python body itself and
  stamped `synced`. No `python_derived_from_recipe_hash` exists because
  no transpile ever ran, and that absence is exactly what the derivation
  reads."""
  assert derive_sync_state(QUIZ_POST_BACKFILL) == STALE_PYTHON
  assert QUIZ_POST_BACKFILL["sync_state"] == "synced"


def test_incident_4_step5_supplies_the_answer_the_missing_field_could_not():
  assert derive_sync_state(STEP5_POST_RUN) == SYNCED
  assert "sync_state" not in STEP5_POST_RUN


def test_every_incident_disagrees_with_its_persisted_field():
  """The single claim Phase 2 rests on. If any of these ever agree by
  accident, the fixture stopped being an incident."""
  for name, fm in [
    ("murmuration", MURMURATION),
    ("solitary", SOLITARY),
    ("quiz pre-backfill", QUIZ_PRE_BACKFILL),
    ("quiz post-backfill", QUIZ_POST_BACKFILL),
    ("step-5 post-run", STEP5_POST_RUN),
  ]:
    derived = derive_sync_state(fm)
    persisted = fm.get("sync_state")
    assert derived != persisted, f"{name}: derived {derived} == persisted {persisted}"


# ---------------------------------------------------------------------
# Purity
# ---------------------------------------------------------------------


def test_the_input_mapping_is_not_mutated():
  fm = dict(MURMURATION)
  before = dict(fm)
  derive_sync_state(fm)
  assert fm == before


def test_a_non_mapping_input_raises_a_typed_error():
  """Degenerate inputs map to defined VALUES; a wrong TYPE is a caller
  bug and says so."""
  with pytest.raises(TypeError):
    derive_sync_state("not a mapping")  # type: ignore[arg-type]
