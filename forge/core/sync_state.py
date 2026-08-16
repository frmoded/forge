"""Derive a note's sync state from its hash lineage.

Phase 1 of the Option C `sync_state` retirement, adopted by the driver
2026-08-16 (`forge-moda-bootstrap/sync-state-ownership-options.md`).
Drain `2026-08-16-2000`.

WHY THIS EXISTS
---------------
`sync_state` has been a PERSISTED frontmatter field with several
independent writers. It is a cache of facts that sit right next to it in
the same frontmatter, and in three days it lied in four different ways:
it claimed stale on an aligned note, it blamed the wrong link, it
certified a Python body the system had manufactured itself, and it went
missing entirely. A cache of adjacent persisted facts can only ever
drift from them.

`recipe_derived_from_description_hash == description_hash` and
`python_derived_from_recipe_hash == recipe_hash` ARE the sync state.
This module computes it, so that no one has to store it.

THIS MODULE IS THE VOCABULARY SPEC. Consumers migrate to it in Phase 2;
nothing here is wired yet, and nothing here writes anything.

Pyodide-safe: pure functions, stdlib only, no I/O. It vendors to the
plugin's engine bundle and must keep working there.

THE VOCABULARY
--------------
Four values, each one earned by a consumer in the Phase 1 inventory:

  `synced`        every derivation the note's source facet implies is
                  current.
  `stale-recipe`  the Recipe is not a current derivation of the
                  Description.
  `stale-python`  the Recipe is current (or is itself the source), and
                  the Python is not a current derivation of the Recipe.
  `unknown`       the lineage needed to answer cannot be evaluated —
                  a legacy or never-stamped note. Callers must treat
                  this as "I do not know", NEVER as `synced`. That
                  instruction is already the documented contract for a
                  missing field (`forge_mcp/schemas.py`); this names it
                  instead of leaving it to a `None`.

The value names the FIRST broken link in the D -> R -> P chain.
Everything downstream of that link is implicitly out of date too — a
Recipe that no longer matches its Description makes the Python stale
whether or not the Python still matches that Recipe.

`stale-both` IS DELIBERATELY ABSENT. It is the plugin's fourth value,
and the Phase 1 inventory found zero consumers that read it (nothing in
any repo branches on any of these values). Under first-broken-link
ordering it is also redundant with `stale-recipe`. Per the drain's §4 it
is flagged for retirement rather than ported. If a consumer ever
genuinely needs to distinguish "and the Python drifted locally as well",
add it together with that consumer, not ahead of one.

WHAT IS AND IS NOT COMPARED
---------------------------
Only STORED values are compared: lineage stamps against facet hashes.
No facet BODY is read and no hash is recomputed. That is the difference
from the plugin's `computeSyncState`, which hashes the note's live text
and compares against the stored hashes — a different question ("has
someone edited this since it was stamped?"). Both are useful; this one
answers "did the derivation that this note claims actually happen, and
against the content that is here now?", which is what every consumer in
the inventory is actually asking.

`source_facet` gates which links are meaningful. Per the constitution's
S9 visibility contract, a facet UPSTREAM of the source renders
`— ignored`, not `— out of date`: a hand-authored Recipe owes the
Description nothing.
"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping, Optional, Tuple

__all__ = [
  "EMPTY_FACET_HASH",
  "STALE_PYTHON",
  "STALE_RECIPE",
  "SYNCED",
  "SYNC_STATES",
  "UNKNOWN",
  "derive_sync_state",
]


SYNCED = "synced"
STALE_RECIPE = "stale-recipe"
STALE_PYTHON = "stale-python"
UNKNOWN = "unknown"

#: The complete vocabulary. Ordered upstream-first, which is also the
#: order the rollup below resolves ties in.
SYNC_STATES: Tuple[str, ...] = (SYNCED, STALE_RECIPE, STALE_PYTHON, UNKNOWN)

#: An absent facet and an empty one hash to the same value, in the
#: plugin (`computeFacetHash`), in forge-mcp (`compute_facet_hash`) and
#: here: both normalize to "" before hashing. So a facet hash equal to
#: this means "there is no body", and that is how absence is detected
#: without reading any body.
EMPTY_FACET_HASH = hashlib.sha256(b"").hexdigest()


# Per-link verdicts. Internal — the note-level vocabulary above is the
# public one.
_CURRENT = "current"
_STALE = "stale"
_UNEVALUABLE = "unevaluable"


def _hash_field(frontmatter: Mapping[str, Any], key: str) -> Optional[str]:
  """A frontmatter value only counts as a hash when it is a string.

  YAML hands back ints, bools, lists and `None` for fields that were
  hand-edited or half-written; none of those is a hash, and all of them
  read as absent rather than raising.
  """
  value = frontmatter.get(key)
  return value if isinstance(value, str) else None


def _link_state(
  parent_hash: Optional[str],
  child_hash: Optional[str],
  lineage_hash: Optional[str],
) -> str:
  """Is `child` a current derivation of `parent`?

  `parent_hash` / `child_hash` are the two facets' own content hashes;
  `lineage_hash` is the child's stamp recording which parent content it
  was derived FROM.
  """
  if parent_hash is None:
    # Never stamped. We cannot tell whether the parent has content, so
    # we cannot judge the link. Not the same as "the parent is empty".
    return _UNEVALUABLE
  if parent_hash == EMPTY_FACET_HASH:
    # Nothing to derive from — a vacuous link, not a broken one.
    return _CURRENT
  if child_hash is None:
    return _UNEVALUABLE
  if child_hash == EMPTY_FACET_HASH:
    # The parent has content and the child does not: the derivation has
    # not happened yet. forge-mcp's note shell reasons identically when
    # it opens a fresh note at `stale-recipe`.
    return _STALE
  if lineage_hash is None:
    # I18 — never certify a derivation that didn't happen. Matching
    # hashes would not help here either: mechanical consistency is not
    # evidence that anything was derived. Absent lineage means no.
    return _STALE
  return _CURRENT if lineage_hash == parent_hash else _STALE


def derive_sync_state(frontmatter: Mapping[str, Any]) -> str:
  """Return one of :data:`SYNC_STATES` for a note's frontmatter.

  Reads (all optional):
    `description_hash`, `recipe_hash`, `python_hash` — each facet's own
    content hash. Equal to :data:`EMPTY_FACET_HASH` means the facet is
    empty or absent.
    `recipe_derived_from_description_hash` — the Description content the
    Recipe was generated from. `recipe_derived_from_source_hash` is the
    pre-v11.6 name for the same value and is accepted as a fallback:
    live notes carry both, and the v11.4 backfill stamps only the old
    one.
    `python_derived_from_recipe_hash` — the Recipe content the Python
    was transpiled from. NOTE: `python_derived_from_source_hash` is NOT
    a fallback for it. Despite the parallel name it holds the
    DESCRIPTION hash (verified on murmuration and every percussion_lab
    note), so reading it here would compare Python's lineage against the
    wrong parent and manufacture a false `synced`.
    `source_facet` — which facet is authoritative. `recipe` and `python`
    mean the facets upstream of them are ignored rather than stale.
    Unrecognized values are treated as `description`, which evaluates
    every link: garbage in this field must never buy a `synced`.

  Never raises on content — every degenerate frontmatter maps to a
  value, because the notes that motivated this module are all
  degenerate in one way or another. A non-Mapping argument is a caller
  bug and raises `TypeError`.
  """
  if not isinstance(frontmatter, Mapping):
    raise TypeError(
      "frontmatter must be a Mapping of frontmatter fields, got "
      f"{type(frontmatter).__name__}"
    )

  description_hash = _hash_field(frontmatter, "description_hash")
  recipe_hash = _hash_field(frontmatter, "recipe_hash")
  python_hash = _hash_field(frontmatter, "python_hash")

  if description_hash is None and recipe_hash is None and python_hash is None:
    # A note with no hash stamps at all — legacy, or authored by
    # something that never stamped. Nothing to derive from, and no
    # `source_facet` value may talk us out of saying so.
    return UNKNOWN

  recipe_lineage = _hash_field(
    frontmatter, "recipe_derived_from_description_hash"
  )
  if recipe_lineage is None:
    recipe_lineage = _hash_field(frontmatter, "recipe_derived_from_source_hash")
  python_lineage = _hash_field(frontmatter, "python_derived_from_recipe_hash")

  source_facet = frontmatter.get("source_facet")
  if not isinstance(source_facet, str):
    source_facet = ""

  if source_facet == "python":
    # Python is the source; Description and Recipe are `— ignored`.
    # Nothing derives from Python, so nothing can be out of date.
    return SYNCED

  if source_facet == "recipe":
    # Recipe is the source. Its relationship to the Description is not
    # a derivation and its absence is not staleness.
    recipe_link = _CURRENT
  else:
    recipe_link = _link_state(description_hash, recipe_hash, recipe_lineage)

  python_link = _link_state(recipe_hash, python_hash, python_lineage)

  # Upstream first: name the first broken link. A definite `stale`
  # outranks an unevaluable sibling — knowing one link is broken is
  # more useful than reporting the whole note unknown.
  if recipe_link == _STALE:
    return STALE_RECIPE
  if python_link == _STALE:
    return STALE_PYTHON
  if _UNEVALUABLE in (recipe_link, python_link):
    return UNKNOWN
  return SYNCED
