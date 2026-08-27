#!/usr/bin/env python3
"""Stamp `inputs:` frontmatter on notes that declare `Input` in their Recipe.

Drain 2026-08-14-2230.

WHY THIS EXISTS. The plugin's reactive stamper is EDIT-triggered: it writes
`derive_inputs_from_recipe`'s answer into a note's frontmatter when the note is
edited in a plugin-loaded vault. A note written straight to disk by a drain — a
migration, a bundle sync, a generated fixture — never receives that event, so it
never gets the field. Drain 2210 found exactly that split:
`music-core/pitched_line.md`, authored live, has `inputs:`;
`forge-tutorial/{03-functions/excited,08-recursion/factorial}.md`, written by
drain 2010's migration, do not.

This is the complementary bundle-time half. It does NOT replace the live
stamper.

WHAT THIS IS NOT. It is not a run-button fix. Drain 2210 established that the
run affordance gates on `type` alone (`forge-button-gate-core.ts` consults one
field), so a missing `inputs:` never hid a button. This closes a
metadata-cache staleness issue for the surfaces that DO read the field — MCP
metadata and the palette.

SCOPE. Only notes whose Recipe contains an `Input` statement are touched.
A note relying on the legacy leading-typed-`Let` inference is left exactly as
it is, matching `derive_inputs_from_recipe`'s own dual-mode split.

Usage:
    python scripts/stamp_inputs.py <vault-dir> [<vault-dir> ...]
    python scripts/stamp_inputs.py --check <vault-dir>   # exit 1 if any drift
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
  sys.path.insert(0, str(_REPO_ROOT))

from forge.recipe.parser import ParseError, derive_inputs_from_recipe  # noqa: E402

_FM_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)
_RECIPE_RE = re.compile(r"^# Recipe\s*$", re.M)
_INPUTS_BLOCK_RE = re.compile(r"^inputs:\n(?:  - .*\n)*", re.M)
_INPUTS_INLINE_RE = re.compile(r"^inputs:.*\n", re.M)
_INPUTS_INLINE_LIST_RE = re.compile(r"^inputs:[ \t]*\[(.*?)\][ \t]*$", re.M)


def _existing_input_names(fm: str) -> list[str] | None:
  """The `inputs:` value already in the frontmatter, as a list of names.

  `None` means the note carries no `inputs:` field at all — distinct from an
  empty list, which is a note that declares it has none.

  Drain 2026-08-16-1800 (retry). YAML writes a sequence two ways, and
  `inputs: [bars, velocity]` is the SAME VALUE as the block form this script
  emits. The comparison used to be against the block SERIALIZATION only, so
  every inline-form note read as permanent drift no matter how right it was:
  `--check` failed on it every run, and the remedy the failure printed would
  have rewritten another vault's notes to change nothing but their
  punctuation. Nine `music-core/percussion_lab` notes blocked the v0.2.360
  release twice on exactly this. Compare values.
  """
  inline = _INPUTS_INLINE_LIST_RE.search(fm)
  if inline is not None:
    body = inline.group(1).strip()
    return [n.strip() for n in body.split(",") if n.strip()] if body else []

  block = _INPUTS_BLOCK_RE.search(fm + "\n")
  if block is not None:
    return [
      line.strip()[2:].strip()
      for line in block.group(0).splitlines()[1:]
      if line.strip().startswith("- ")
    ]
  return None


def _recipe_body(text: str) -> str | None:
  """The Recipe facet's body, or None when the note has no Recipe."""
  m = _RECIPE_RE.search(text)
  if not m:
    return None
  rest = text[m.end():]
  # Stop at the next top-level facet heading, if any.
  nxt = re.search(r"^# \w", rest, re.M)
  return rest[: nxt.start()] if nxt else rest


def _render_inputs(names: list[str]) -> str:
  return "inputs:\n" + "".join(f"  - {n}\n" for n in names)


def stamp_note(path: Path, *, write: bool = True) -> bool:
  """Bring one note's `inputs:` frontmatter in line with its Recipe.

  Returns True if the note needed stamping. Idempotent: a note already
  carrying the deriver's answer is left byte-identical and reports False, so
  this can run on every sync without churning files.

  `write=False` answers the same question without touching the file — the
  mode `--check` runs in. Drain 2026-08-16-0910: `--check` used to change
  only the printed verb and the exit code while `stamp_vault` wrote either
  way, so the check MUTATED the vault it was inspecting. Wired into the
  release preflight that means every cut silently rewrites bundled content,
  and a red CI run goes green on retry with an unexplained working-tree
  change. A gate must not fix what it is gating.
  """
  text = path.read_text(encoding="utf-8")
  fm_match = _FM_RE.match(text)
  if not fm_match:
    return False  # no frontmatter — not a note this pass owns

  recipe = _recipe_body(text)
  if not recipe:
    return False

  # Drain 2026-08-27-1200 — a Recipe that does not PARSE has no inputs to
  # derive, and a vault may legitimately contain one: chapter 3's
  # fix_the_call.md is broken on purpose (principle 10, "show one real
  # failure"), and any learner mid-edit produces the same state. Before this
  # guard, one such note raised ParseError out of stamp_vault and took the
  # whole sweep down with a traceback that did not even name the file --
  # which meant a release preflight failing with no usable diagnostic.
  try:
    decls = derive_inputs_from_recipe(recipe)
  except ParseError:
    return False
  # Only notes with an actual `Input` statement are in scope. The deriver
  # falls back to legacy typed-Let inference when none exist; that path is
  # deliberately NOT stamped here (drain §4).
  if not re.search(r"^\s*Input\s+\w+", recipe, re.M):
    return False
  if not decls:
    return False

  names = [d.name for d in decls]
  fm = fm_match.group(1)

  desired = _render_inputs(names).rstrip("\n")

  if _existing_input_names(fm) == names:
    return False  # already correct — no write, no churn, whichever YAML form

  if not write:
    return True  # --check: it needs stamping, and we say so without doing it

  # Drop any prior inputs: representation (block or inline), then append.
  new_fm = _INPUTS_BLOCK_RE.sub("", fm + "\n")
  new_fm = _INPUTS_INLINE_RE.sub("", new_fm)
  new_fm = new_fm.rstrip("\n")
  new_fm = f"{new_fm}\n{desired}" if new_fm else desired

  path.write_text(f"---\n{new_fm}\n---\n{text[fm_match.end():]}", encoding="utf-8")
  return True


def stamp_vault(root: Path, *, write: bool = True) -> list[Path]:
  """Stamp every `.md` under `root`. Returns the paths that needed stamping.

  With `write=False` nothing is written and the return value is the list of
  notes that WOULD have been stamped — what `--check` reports."""
  changed: list[Path] = []
  for p in sorted(root.rglob("*.md")):
    if any(part.startswith(".") for part in p.relative_to(root).parts):
      continue  # skip .obsidian/, .forge/, etc.
    if stamp_note(p, write=write):
      changed.append(p)
  return changed


def main(argv: list[str]) -> int:
  check = "--check" in argv
  roots = [Path(a) for a in argv if not a.startswith("-")]
  if not roots:
    print(__doc__)
    return 2
  total: list[Path] = []
  for root in roots:
    if not root.is_dir():
      print(f"ERROR: not a directory: {root}", file=sys.stderr)
      return 2
    changed = stamp_vault(root, write=not check)
    total.extend(changed)
    for p in changed:
      print(f"  {'DRIFT' if check else 'stamped'}: {p}")
  if not total:
    print("  all notes already carry the derived inputs: — nothing to do")
  if check and total:
    print(
      "\nRun without --check to stamp them.", file=sys.stderr
    )
    return 1
  return 0


if __name__ == "__main__":
  raise SystemExit(main(sys.argv[1:]))
