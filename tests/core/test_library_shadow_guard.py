"""Guard: no vault note shadows an engine library function it also calls.

Drain 2026-08-19-1100(b). The defect: a note whose Recipe calls its OWN
basename resolves to itself rather than to the engine library function
of that name, and recurses until the interpreter gives up. It has now
cost two cohort-facing failures and two driver adjudications:

  create_water_particles.md  deleted 3009f81 (adjudicated)
  create_ink_particles.md    deleted by this drain — it broke every
                             `simulation` run, the step-8 daily-
                             regression surface

Both were found by a human running the demo, never by the suite. The
sweep is cheap, so it belongs in the suite.

WHAT FAILS vs WHAT WARNS
------------------------
FAILS: self-call AND a library function of that name exists — the note
is shadowing something real, so the call had a legitimate target and
silently got the note instead. This is the recursion pathology.

WARNS: self-call with no library function of that name. Nothing is being
shadowed; the note is simply referring to itself, which may be a
different bug (`random_name.md` self-calls and fails on a missing
argument) or, in principle, deliberate. Failing on these would make the
guard adjudicate content questions it has no basis to decide, so they
are printed for a human instead. Per this drain's §1, adjudication
reported in FEEDBACK.

VAULT RESOLUTION is deliberately NOT via tests/moda/_helpers.py's
_find_vault: that resolves to a stale sibling (drain 2026-08-19-1110's
subject) which still contains the deleted notes, so a guard reading it
would pass while the shipping vaults were broken. This module reads
~/projects/<vault> directly, overridable per-vault by env var.
"""
import ast
import os
import re

import pytest

#: Source-of-truth vaults, and the env var that overrides each.
VAULTS = {
  "forge-moda": "FORGE_MODA_VAULT_PATH",
  "music-theory": "FORGE_MUSIC_THEORY_VAULT_PATH",
  "music-core": "FORGE_MUSIC_CORE_VAULT_PATH",
  "forge-tutorial": "FORGE_TUTORIAL_VAULT_PATH",
}

_ENGINE = os.path.join(os.path.dirname(__file__), "..", "..", "forge")


def vault_path(name):
  override = os.environ.get(VAULTS[name])
  if override:
    return override if os.path.isdir(override) else None
  p = os.path.expanduser(f"~/projects/{name}")
  return p if os.path.isdir(p) else None


def declared_domains(vault):
  """`domains = [...]` from the vault's forge.toml."""
  toml = os.path.join(vault, "forge.toml")
  if not os.path.isfile(toml):
    return []
  m = re.search(r"^domains\s*=\s*\[(.*?)\]", open(toml).read(), re.M | re.S)
  return re.findall(r'"([^"]+)"', m.group(1)) if m else []


def library_function_names(domains):
  """Public callables exported by forge.core.lib plus each domain lib.

  AST-introspected rather than imported: importing forge.moda.lib pulls
  numpy and the music stack in, which this guard has no need for. Same
  technique the transpile service uses to build its catalog.
  """
  names = set()
  for mod in ["core", *domains]:
    path = os.path.join(_ENGINE, mod, "lib.py")
    if not os.path.isfile(path):
      continue
    tree = ast.parse(open(path).read())
    for node in tree.body:
      if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if not node.name.startswith("_"):
          names.add(node.name)
  return names


def recipe_body(text):
  """The `# Recipe` section, or '' when the note has none."""
  out, inside = [], False
  for line in text.splitlines():
    if line.startswith("# Recipe"):
      inside = True
      continue
    if inside and line.startswith("# "):
      break
    if inside:
      out.append(line)
  return "\n".join(out)


def self_calling_notes(vault):
  """[(basename, relpath)] for notes whose Recipe calls [[basename]].

  Dot-directories are pruned — `.obsidian/` holds the installed plugin's
  bundled copies of OTHER vaults and `.forge/` holds edge snapshots;
  neither is authored content in this vault. Same lesson as drain
  2026-08-17-1210.
  """
  hits = []
  for root, dirs, files in os.walk(vault):
    dirs[:] = [d for d in dirs if not d.startswith(".")]
    for fn in files:
      if not fn.endswith(".md"):
        continue
      base = fn[: -len(".md")]
      full = os.path.join(root, fn)
      try:
        text = open(full).read()
      except OSError:
        continue
      if f"[[{base}]]" in recipe_body(text):
        hits.append((base, os.path.relpath(full, vault)))
  return hits


@pytest.mark.parametrize("vault_name", sorted(VAULTS))
def test_no_note_shadows_a_library_function_it_calls(vault_name, capsys):
  vault = vault_path(vault_name)
  if vault is None:
    pytest.skip(f"{vault_name} vault not found")

  lib_names = library_function_names(declared_domains(vault))
  # Non-vacuity: a guard comparing against an empty library set could
  # never fail, which is exactly the silent-pass shape (I23/L32) this
  # class of bug keeps hiding in.
  assert lib_names, (
    f"no engine library functions resolved for {vault_name} "
    f"(domains={declared_domains(vault)}); the guard would be vacuous"
  )

  self_callers = self_calling_notes(vault)
  shadowing = [(b, p) for b, p in self_callers if b in lib_names]
  plain = [(b, p) for b, p in self_callers if b not in lib_names]

  if plain:
    # Reported, not failed — see the module docstring.
    with capsys.disabled():
      print(f"\n  [shadow-guard] {vault_name}: self-calling notes that "
            f"shadow nothing (not a failure): "
            f"{[b for b, _ in plain]}")

  assert not shadowing, (
    f"{vault_name}: these notes call their own basename while an engine "
    f"library function of that name exists, so the call resolves to the "
    f"note and recurses forever: {shadowing}. Delete the note (the "
    f"library function is the real callee) or rename it so it stops "
    f"shadowing. Precedent: create_water_particles.md (3009f81), "
    f"create_ink_particles.md (drain 2026-08-19-1100)."
  )


def test_the_guard_detects_the_shape_it_was_written_for(tmp_path):
  """Non-vacuity proof on a fixture, independent of any real vault.

  Without this, the parametrized test above would go green the moment
  the last offending note was deleted and stay green even if the
  detection logic were broken.
  """
  (tmp_path / "forge.toml").write_text('domains = ["moda"]\n')
  (tmp_path / "create_ink_particles.md").write_text(
    "---\ntype: action\n---\n\n# Description\n\nx\n\n# Recipe\n\n"
    "Let s = Call [[create_ink_particles]] with state=state.\nReturn s.\n"
  )
  (tmp_path / "innocent.md").write_text(
    "---\ntype: action\n---\n\n# Recipe\n\nCall [[create_chamber]].\n"
  )

  lib_names = library_function_names(declared_domains(str(tmp_path)))
  assert "create_ink_particles" in lib_names, "fixture assumes the real moda lib"

  callers = self_calling_notes(str(tmp_path))
  assert [b for b, _ in callers] == ["create_ink_particles"], (
    "must flag the self-caller and only the self-caller"
  )
  assert callers[0][0] in lib_names, "and must recognise it as shadowing"


def test_a_self_call_outside_the_recipe_section_is_not_flagged(tmp_path):
  """A note may legitimately name itself in prose. Only the Recipe is
  executable, so only the Recipe is scanned."""
  (tmp_path / "forge.toml").write_text('domains = ["moda"]\n')
  (tmp_path / "create_ink_particles.md").write_text(
    "---\ntype: action\n---\n\n# Description\n\n"
    "This note wraps [[create_ink_particles]] from the library.\n\n"
    "# Recipe\n\nCall [[create_chamber]].\n"
  )
  assert self_calling_notes(str(tmp_path)) == []
