"""Shared fixtures for the 25-block MoDa partition.

The moda block snippets live in a sibling vault (the authoring vault the
backend's FORGE_MODA_VAULT_PATH defaults to, or the promoted
distributable). They are not part of the forge package, so these tests
resolve them through the same registry/resolver machinery the backend
uses and skip the whole partition if no vault is reachable (fresh
clone / CI without the sibling repo).

Plain (non-fixture) helpers — `make_state`, `_find_vault` — live in
`_helpers.py` next door so test modules can import them by name
without the `from tests.moda.conftest import ...` indirection. The
fixtures below call the helpers internally.
"""
import pytest

from forge.core.registry import SnippetRegistry, GraphResolver
from forge.core.executor import extract_python, exec_python

from tests.moda._helpers import _find_vault


@pytest.fixture(scope="session")
def moda_vault():
    path = _find_vault()
    if path is None:
        pytest.skip(
            "no moda vault found (set FORGE_MODA_VAULT_PATH or clone "
            "forge-moda alongside forge)"
        )
    return path


@pytest.fixture(scope="session")
def resolver(moda_vault):
    reg = SnippetRegistry()
    reg.scan(moda_vault)
    return GraphResolver(reg), reg, moda_vault


@pytest.fixture(scope="session")
def run_block(resolver):
    res, reg, vault = resolver

    def _run(snippet_id, *args, **inputs):
        snip = res.resolve(snippet_id)
        code = extract_python(snip["body"])
        _, result = exec_python(
            code, inputs, res, args=args,
            vault_path=vault, registry=reg, snippet_id=snip["snippet_id"],
        )
        return result

    return _run


@pytest.fixture(scope="session")
def block_source(resolver):
    res, _reg, _vault = resolver

    def _src(snippet_id):
        return extract_python(res.resolve(snippet_id)["body"])

    return _src
