"""Static conformance for the moda blocks — V2 vocabulary.

Drain 2026-08-20-1210(b). The V1 test this replaces asserted that every
note carried a `# Python` facet whose `context.compute("peer")` calls
matched a hand-maintained peer set. That invariant describes an
architecture that no longer exists: V2 notes declare their dependencies
as Recipe wikilinks and have no `# Python` facet at all. Against the
shipping vault it failed on 25 of 25 notes — not because the vault was
wrong, but because the test was reading a vocabulary the project
retired. Its SPEC also still enumerated two notes the driver had
deleted.

Retired on forge-core's adjudication, and replaced rather than dropped:
the *spirit* — dependency correctness, checked statically, per note —
is worth keeping. The V2 form of it is that **every wikilink in a
Recipe resolves**, either to a vault note or to an engine library
function. That is the property whose violation produced this session's
two cohort-facing failures (`create_water_particles`,
`create_ink_particles`), and unlike a hardcoded peer set it needs no
maintenance as the vault evolves.

What this deliberately does NOT do is re-encode expected peer sets in
V2 clothing. A hand-maintained list of who-calls-whom was the part that
rotted; asserting resolvability instead keeps the guarantee and drops
the upkeep.
"""
import ast
import os
import re

import pytest

_ENGINE = os.path.join(os.path.dirname(__file__), "..", "..", "forge")

#: E-- language primitives: valid `[[...]]` targets that are neither
#: vault notes nor library functions. `print` is documented as such in
#: forge/recipe/parser.py's own grammar docstring
#: (`Call [[print]] with text="hi".`).
#:
#: FINDING (drain 2026-08-20-1210, reported in FEEDBACK): the ENGINE has
#: no authoritative primitive registry. The plugin has one —
#: `LANGUAGE_PRIMITIVES` in the TS palette code, hardcoded there per
#: drain 1300 ("language primitives are plugin-registered; not
#: vault-configurable") — but nothing engine-side enumerates them, so
#: this set is curated by hand and can drift. It is deliberately
#: minimal: a name only belongs here with a citation.
_LANGUAGE_PRIMITIVES = {"print"}

#: `[[target]]` — the only dependency vocabulary V2 Recipes use.
_WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")


def _library_function_names():
    """Public callables in forge.core.lib + forge.moda.lib.

    AST-read rather than imported: this is a static test and has no
    business pulling numpy in to answer a name question.
    """
    names = set()
    for mod in ("core", "moda"):
        path = os.path.join(_ENGINE, mod, "lib.py")
        if not os.path.isfile(path):
            continue
        for node in ast.parse(open(path).read()).body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("_"):
                    names.add(node.name)
    return names


def _recipe_body(text):
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


def _notes(vault):
    """{basename: (relpath, text)} for authored notes, dot-dirs pruned.

    `.obsidian/` holds the installed plugin's copies of OTHER vaults and
    `.forge/` holds edge snapshots; neither is authored content here
    (drain 2026-08-17-1210's lesson).
    """
    found = {}
    for root, dirs, files in os.walk(vault):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fn in files:
            if not fn.endswith(".md"):
                continue
            full = os.path.join(root, fn)
            try:
                found[fn[: -len(".md")]] = (os.path.relpath(full, vault), open(full).read())
            except OSError:
                continue
    return found


def _note_ids(vault):
    return sorted(_notes(vault))


@pytest.fixture(scope="module")
def vault_notes(moda_vault):
    return _notes(moda_vault)


def test_the_vault_has_notes_to_check(vault_notes):
    """Non-vacuity. Every assertion below is parameterized over the
    vault's contents, so an empty or mis-resolved vault would make the
    whole module pass while checking nothing — the silent-pass shape
    (I23) that let the stale-vault binding survive so long."""
    assert len(vault_notes) > 20, (
        f"expected the moda vault's full note set, found {len(vault_notes)}"
    )


def test_the_library_names_resolved(vault_notes):
    """Second non-vacuity guard: if the library read returned nothing,
    every wikilink would look unresolvable and the parameterized test
    below would fail for the wrong reason — or, if inverted, pass."""
    assert "create_water_particles" in _library_function_names()


def _all_note_ids():
    """Parameter source. Resolved at collection time from the same
    candidate list the fixtures use."""
    from tests.moda._helpers import _find_vault
    vault = _find_vault()
    return _note_ids(vault) if vault else []


@pytest.mark.parametrize("note_id", _all_note_ids())
def test_every_recipe_wikilink_resolves(note_id, vault_notes, moda_vault):
    """Per-note so a dangling link names its own note.

    A target resolves if it is a vault note, an engine library
    function, or a language primitive. Anything else is a link into
    nothing — the shape that
    broke `simulation` twice this session.
    """
    relpath, text = vault_notes[note_id]
    targets = sorted(set(_WIKILINK.findall(_recipe_body(text))))
    if not targets:
        pytest.skip(f"{note_id}: no Recipe wikilinks")

    known_notes = set(vault_notes)
    known_lib = _library_function_names()
    dangling = [
        t for t in targets
        if t not in known_notes
        and t not in known_lib
        and t not in _LANGUAGE_PRIMITIVES
    ]

    assert not dangling, (
        f"{relpath}: Recipe references {dangling}, which resolve to neither a "
        f"vault note nor an engine library function. A call to a name that "
        f"does not exist fails at run time with SnippetResolutionError — "
        f"precedent: simulation, broken twice this session by exactly this."
    )
