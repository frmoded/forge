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


def test_domain_globals_empty_is_core_only():
    assert _domain_globals_for([]) == {}


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


def test_core_only_has_neither_domain_global():
    for name in ("ParticleState", "music21"):
        code = f"def compute(context):\n    return {name}\n"
        with pytest.raises(Exception):
            _run(code, [])


def test_base_names_always_injected_regardless_of_domains():
    code = "def compute(context):\n    return (numpy.pi, math.pi, random.random() >= 0.0)\n"
    for domains in (None, [], ["moda"], ["music"]):
        out = _run(code, domains)
        assert out[2] is True  # base names present in every scope
