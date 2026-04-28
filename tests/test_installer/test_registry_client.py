import json
import time
from pathlib import Path
import pytest
import responses
from forge.installer.registry_client import fetch_index, lookup, clear_cache
from forge.installer.exceptions import ValidationError, SnippetNotFoundError

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
  return json.loads((FIXTURES / name).read_text())


@pytest.fixture(autouse=True)
def reset_cache():
  clear_cache()
  yield
  clear_cache()


@responses.activate
def test_fetch_valid_index():
  data = _load_fixture("valid_index.json")
  responses.add(responses.GET, "https://example.com/index.json", json=data, status=200)
  result = fetch_index("https://example.com/index.json")
  assert result["schema_version"] == "1"
  assert "forge-core" in result["vaults"]


@responses.activate
def test_rejects_unsupported_schema_version():
  responses.add(
    responses.GET,
    "https://example.com/index.json",
    json={"schema_version": "2", "vaults": {}},
    status=200,
  )
  with pytest.raises(ValidationError, match="schema_version"):
    fetch_index("https://example.com/index.json")


@responses.activate
def test_rejects_missing_schema_version():
  responses.add(
    responses.GET,
    "https://example.com/index.json",
    json={"vaults": {}},
    status=200,
  )
  with pytest.raises(ValidationError):
    fetch_index("https://example.com/index.json")


@responses.activate
def test_rejects_non_https_tarball():
  bad = {
    "schema_version": "1",
    "vaults": {
      "x": {
        "latest": "0.1.0",
        "versions": {
          "0.1.0": {
            "tarball": "http://example.com/x.tar.gz",
            "sha256": "0" * 64,
          }
        }
      }
    },
  }
  responses.add(responses.GET, "https://example.com/index.json", json=bad, status=200)
  with pytest.raises(ValidationError, match="HTTPS"):
    fetch_index("https://example.com/index.json")


@responses.activate
def test_rejects_bad_sha_format():
  bad = {
    "schema_version": "1",
    "vaults": {
      "x": {
        "latest": "0.1.0",
        "versions": {
          "0.1.0": {
            "tarball": "https://example.com/x.tar.gz",
            "sha256": "ABCDEF",  # too short and uppercase
          }
        }
      }
    },
  }
  responses.add(responses.GET, "https://example.com/index.json", json=bad, status=200)
  with pytest.raises(ValidationError, match="sha256"):
    fetch_index("https://example.com/index.json")


@responses.activate
def test_rejects_invalid_semver():
  bad = {
    "schema_version": "1",
    "vaults": {
      "x": {
        "latest": "not-a-version",
        "versions": {
          "not-a-version": {
            "tarball": "https://example.com/x.tar.gz",
            "sha256": "0" * 64,
          }
        }
      }
    },
  }
  responses.add(responses.GET, "https://example.com/index.json", json=bad, status=200)
  with pytest.raises(ValidationError, match="SemVer"):
    fetch_index("https://example.com/index.json")


@responses.activate
def test_rejects_latest_not_in_versions():
  bad = {
    "schema_version": "1",
    "vaults": {
      "x": {
        "latest": "9.9.9",
        "versions": {
          "0.1.0": {
            "tarball": "https://example.com/x.tar.gz",
            "sha256": "0" * 64,
          }
        }
      }
    },
  }
  responses.add(responses.GET, "https://example.com/index.json", json=bad, status=200)
  with pytest.raises(ValidationError, match="latest"):
    fetch_index("https://example.com/index.json")


def test_lookup_returns_latest_when_version_omitted():
  index = _load_fixture("valid_index.json")
  result = lookup(index, "forge-core")
  assert result["version"] == "0.2.0"
  assert result["tarball"] == "https://github.com/frmoded/forge-core/archive/refs/tags/v0.2.0.tar.gz"
  assert len(result["sha256"]) == 64


def test_lookup_returns_specific_version():
  index = _load_fixture("valid_index.json")
  result = lookup(index, "forge-core", version="0.1.0")
  assert result["version"] == "0.1.0"
  assert "v0.1.0" in result["tarball"]


def test_lookup_unknown_vault_raises():
  index = _load_fixture("valid_index.json")
  with pytest.raises(SnippetNotFoundError, match="not in registry"):
    lookup(index, "nonexistent")


def test_lookup_unknown_version_raises():
  index = _load_fixture("valid_index.json")
  with pytest.raises(SnippetNotFoundError, match="version"):
    lookup(index, "forge-core", version="9.9.9")


@responses.activate
def test_cache_serves_within_ttl():
  data = _load_fixture("valid_index.json")
  responses.add(responses.GET, "https://example.com/index.json", json=data, status=200)
  fetch_index("https://example.com/index.json")
  fetch_index("https://example.com/index.json")
  fetch_index("https://example.com/index.json")
  assert len(responses.calls) == 1


@responses.activate
def test_cache_keyed_by_url():
  data = _load_fixture("valid_index.json")
  responses.add(responses.GET, "https://a.example.com/i.json", json=data, status=200)
  responses.add(responses.GET, "https://b.example.com/i.json", json=data, status=200)
  fetch_index("https://a.example.com/i.json")
  fetch_index("https://b.example.com/i.json")
  assert len(responses.calls) == 2
