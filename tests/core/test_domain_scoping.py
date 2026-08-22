"""Domain scoping (constitution B9): manifest `domains` parsing +
executor global-injection filter.
"""
import pytest

from forge.core.manifest import read_manifest
from forge.core.executor import _domain_globals_for, exec_python


# --------------------------------------------------------------------------
# Manifest parsing
# --------------------------------------------------------------------------

def _write_manifest(tmp_path, body):
    (tmp_path / "forge.toml").write_text(body)
    return tmp_path


def test_manifest_domains_absent_is_none(tmp_path):
    _write_manifest(tmp_path, 'name = "test-vault"\nversion = "0.1.0"\ndescription = "d"\n')
    assert read_manifest(tmp_path).domains is None  # None => "all" (back-compat)


def test_manifest_domains_explicit_list(tmp_path):
    _write_manifest(
        tmp_path,
        'name = "test-vault"\nversion = "0.1.0"\ndescription = "d"\ndomains = ["moda"]\n',
    )
    assert read_manifest(tmp_path).domains == ["moda"]


def test_manifest_domains_empty_list_is_core_only(tmp_path):
    _write_manifest(
        tmp_path,
        'name = "test-vault"\nversion = "0.1.0"\ndescription = "d"\ndomains = []\n',
    )
    assert read_manifest(tmp_path).domains == []  # explicit opt-out, not None


def test_manifest_domains_multi(tmp_path):
    _write_manifest(
        tmp_path,
        'name = "test-vault"\nversion = "0.1.0"\ndescription = "d"\n'
        'domains = ["moda", "music"]\n',
    )
    assert read_manifest(tmp_path).domains == ["moda", "music"]


def test_manifest_domains_must_be_string_list(tmp_path):
    _write_manifest(
        tmp_path,
        'name = "test-vault"\nversion = "0.1.0"\ndescription = "d"\ndomains = [1, 2]\n',
    )
    with pytest.raises(Exception):
        read_manifest(tmp_path)


# --------------------------------------------------------------------------
# Executor global-injection filter
# --------------------------------------------------------------------------

def test_domain_globals_none_includes_all():
    g = _domain_globals_for(None)
    assert "ParticleState" in g          # moda
    assert "music21" in g or "stream" in g  # music


def test_domain_globals_empty_is_unconfigured_not_core_only():
    """Drain 2026-08-22-2200 REVERSED this cell. It asserted
    `_domain_globals_for([]) == {}` — `[]` as deny-all — which is what
    the v0.2.14 fresh-vault stub writes, so honouring declared domains
    would have stripped every chip in every fresh vault. Kept (not
    deleted) as the record of the semantics change: `[]` now means
    unconfigured, and the strict cells below are unchanged."""
    g = _domain_globals_for([])
    assert g != {}
    assert "ParticleState" in g and "music21" in g


def test_domain_globals_moda_only():
    g = _domain_globals_for(["moda"])
    assert "ParticleState" in g and "Particle" in g
    assert "music21" not in g and "stream" not in g


def test_domain_globals_music_only():
    g = _domain_globals_for(["music"])
    assert "music21" in g
    assert "ParticleState" not in g


def _run(code, domains):
    _, result = exec_python(code, {}, domains=domains)
    return result


def test_moda_snippet_under_moda_domain_can_use_particlestate():
    code = (
        "def compute(context):\n"
        "    import numpy\n"
        "    return ParticleState(tick=0, ids=numpy.array([]),"
        " types=numpy.array([],dtype=object), xs=numpy.array([]),"
        " ys=numpy.array([]), headings=numpy.array([]),"
        " speeds=numpy.array([]), masses=numpy.array([],dtype=object),"
        " width=1.0, height=1.0).tick\n"
    )
    assert _run(code, ["moda"]) == 0


def test_moda_snippet_under_music_domain_nameerrors_on_particlestate():
    code = "def compute(context):\n    return ParticleState\n"
    with pytest.raises(Exception):  # NameError surfaces as SnippetExecError
        _run(code, ["music"])


def test_music_name_absent_under_moda_domain():
    code = "def compute(context):\n    return music21\n"
    with pytest.raises(Exception):
        _run(code, ["moda"])


def test_unconfigured_domains_reach_both_domain_globals():
    """Companion to the above: same reversal at the exec level. Was
    "core-only rejects both"; `[]` no longer restricts, so both bind.
    The genuine restriction cases (['moda'] / ['music']) keep their own
    tests and still exclude."""
    for name in ("ParticleState", "music21"):
        code = f"def compute(context):\n    return {name}\n"
        assert _run(code, []) is not None


def test_base_names_always_injected_regardless_of_domains():
    code = "def compute(context):\n    return (numpy.pi, math.pi, random.random() >= 0.0)\n"
    for domains in (None, [], ["moda"], ["music"]):
        out = _run(code, domains)
        assert out[2] is True  # base names present in every scope


# ---------------------------------------------------------------------
# Drain 2026-08-22-2200 — `domains=[]` must not silently strip every
# domain chip, and a gate that DOES exclude must say so legibly.
#
# `[]` is exactly what the v0.2.14 fresh-vault forge.toml stub writes.
# Read as "deny all", it turns every domain-chip note in a fresh vault
# into `name 'create_chamber' is not defined` the moment any caller
# starts honouring declared domains. Read as "unconfigured" — which is
# what a stub means — it behaves like None. Adjudication (a) + (c):
# permissive for None/[], legible error whenever the gate excludes.

def test_empty_domains_means_unconfigured_not_deny_all():
    g = _domain_globals_for([])
    assert "ParticleState" in g, "domains=[] must not strip the moda bundle"
    assert "music21" in g, "domains=[] must not strip the music bundle"


def test_domain_matrix_is_pinned():
    """None / [] / ['moda'] / ['music'] in one place, so a future change
    to the gate has to state which cell it is moving."""
    assert "ParticleState" in _domain_globals_for(None)
    assert "music21" in _domain_globals_for(None)

    assert "ParticleState" in _domain_globals_for([])
    assert "music21" in _domain_globals_for([])

    assert "ParticleState" in _domain_globals_for(["moda"])
    assert "music21" not in _domain_globals_for(["moda"])

    assert "music21" in _domain_globals_for(["music"])
    assert "ParticleState" not in _domain_globals_for(["music"])


def test_a_moda_chip_runs_under_empty_domains():
    """The end-to-end shape of the CC repro: a fresh vault's stub
    declares `domains = []`, and a moda chip call must still bind."""
    code = "def compute(context):\n    return create_chamber(width=8, height=6).width\n"
    assert _run(code, []) == 8


def test_excluded_domain_chip_fails_legibly_not_as_a_bare_nameerror():
    """(c): when the gate genuinely excludes a domain, the author needs
    to know WHY. `name 'create_chamber' is not defined` names neither
    the domain nor the file that decided it."""
    code = "def compute(context):\n    return create_chamber(width=8, height=6)\n"
    with pytest.raises(Exception) as excinfo:
        _run(code, ["music"])
    message = str(excinfo.value)
    assert "create_chamber" in message
    assert "moda" in message, "must name the domain that provides it"
    assert "forge.toml" in message, "must point at the file that decides"
    assert "domains" in message


def test_a_genuinely_unknown_name_still_reports_plainly():
    """Non-vacuity for the hint: a typo that no domain provides must NOT
    acquire a misleading domain explanation."""
    code = "def compute(context):\n    return not_a_chip_anywhere\n"
    with pytest.raises(Exception) as excinfo:
        _run(code, ["music"])
    message = str(excinfo.value)
    assert "not_a_chip_anywhere" in message
    assert "forge.toml" not in message
