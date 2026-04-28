import hashlib
from pathlib import Path
from unittest.mock import patch
import pytest
from forge.core.executor import SnippetExecError


def _fake_download(payload):
  """Returns a download_to_file replacement that writes the given bytes."""
  def _impl(url, dest_path, timeout=30):
    Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
    Path(dest_path).write_bytes(payload)
  return _impl


def test_cache_miss_downloads_and_verifies(run_builtin, monkeypatch, tmp_path):
  monkeypatch.setenv("FORGE_CACHE_DIR", str(tmp_path))
  payload = b"tarball-bytes"
  expected_sha = hashlib.sha256(payload).hexdigest()

  with patch("forge.installer.http.download_to_file", side_effect=_fake_download(payload)) as dl:
    _, result = run_builtin(
      "forge/registry/fetch",
      tarball_url="https://example.com/x.tar.gz",
      expected_sha256=expected_sha,
    )

  assert dl.call_count == 1
  cached = tmp_path / "tarballs" / f"{expected_sha}.tar.gz"
  assert Path(result) == cached
  assert cached.read_bytes() == payload


def test_cache_hit_skips_download(run_builtin, monkeypatch, tmp_path):
  monkeypatch.setenv("FORGE_CACHE_DIR", str(tmp_path))
  payload = b"already-here"
  expected_sha = hashlib.sha256(payload).hexdigest()
  cache_path = tmp_path / "tarballs" / f"{expected_sha}.tar.gz"
  cache_path.parent.mkdir(parents=True, exist_ok=True)
  cache_path.write_bytes(payload)

  with patch("forge.installer.http.download_to_file") as dl:
    _, result = run_builtin(
      "forge/registry/fetch",
      tarball_url="https://example.com/x.tar.gz",
      expected_sha256=expected_sha,
    )

  assert dl.call_count == 0
  assert Path(result) == cache_path


def test_sha_mismatch_raises(run_builtin, monkeypatch, tmp_path):
  monkeypatch.setenv("FORGE_CACHE_DIR", str(tmp_path))
  payload = b"tarball-bytes"
  wrong_sha = "0" * 64

  with patch("forge.installer.http.download_to_file", side_effect=_fake_download(payload)):
    with pytest.raises(SnippetExecError) as exc:
      run_builtin(
        "forge/registry/fetch",
        tarball_url="https://example.com/x.tar.gz",
        expected_sha256=wrong_sha,
      )
  assert "hash mismatch" in str(exc.value).lower() or "0000" in str(exc.value)


def test_corrupt_cache_is_detected(run_builtin, monkeypatch, tmp_path):
  """If a cached tarball's bytes don't match its SHA filename, fail loudly."""
  monkeypatch.setenv("FORGE_CACHE_DIR", str(tmp_path))
  expected_sha = hashlib.sha256(b"good").hexdigest()
  cache_path = tmp_path / "tarballs" / f"{expected_sha}.tar.gz"
  cache_path.parent.mkdir(parents=True, exist_ok=True)
  cache_path.write_bytes(b"corrupt")  # wrong contents

  with pytest.raises(SnippetExecError):
    run_builtin(
      "forge/registry/fetch",
      tarball_url="https://example.com/x.tar.gz",
      expected_sha256=expected_sha,
    )
