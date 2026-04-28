import io
import tarfile
from pathlib import Path
import pytest
from forge.core.executor import SnippetExecError
from forge.core.manifest import Manifest


_MANIFEST_TOML = """\
name = "demo-vault"
version = "0.1.0"
description = "A vault for tests."
"""


def _add(tar, name, content):
  data = content.encode("utf-8")
  info = tarfile.TarInfo(name=name)
  info.size = len(data)
  info.mode = 0o644
  tar.addfile(info, io.BytesIO(data))


def _make_tarball(path, wrapper="demo-vault-0.1.0", manifest_text=_MANIFEST_TOML, extra=None):
  with tarfile.open(path, "w:gz") as tar:
    _add(tar, f"{wrapper}/forge.toml", manifest_text)
    _add(tar, f"{wrapper}/snippets/hello.md", "---\ntype: action\n---\n# Python\n```python\ndef run(c): return 1\n```\n")
    if extra:
      for name, content in extra:
        _add(tar, f"{wrapper}/{name}", content)


def test_extract_strips_wrapper_and_returns_manifest(run_builtin, tmp_path):
  tarball = tmp_path / "demo.tar.gz"
  _make_tarball(tarball)
  target = tmp_path / "out"

  _, result = run_builtin(
    "forge/vault/extract",
    tarball_path=str(tarball),
    target_dir=str(target),
  )

  assert result["vault_dir"] == str(target)
  assert (target / "forge.toml").is_file()
  assert (target / "snippets" / "hello.md").is_file()
  assert not (target / "demo-vault-0.1.0").exists()
  m = result["manifest"]
  assert isinstance(m, Manifest)
  assert m.name == "demo-vault"
  assert m.version == "0.1.0"


def test_extract_creates_target_if_missing(run_builtin, tmp_path):
  tarball = tmp_path / "demo.tar.gz"
  _make_tarball(tarball)
  target = tmp_path / "deep" / "nested" / "out"

  _, result = run_builtin(
    "forge/vault/extract",
    tarball_path=str(tarball),
    target_dir=str(target),
  )
  assert (target / "forge.toml").is_file()
  assert result["manifest"].name == "demo-vault"


def test_extract_missing_manifest_fails(run_builtin, tmp_path):
  tarball = tmp_path / "no-manifest.tar.gz"
  with tarfile.open(tarball, "w:gz") as tar:
    _add(tar, "demo-vault-0.1.0/snippets/x.md", "no manifest here\n")
  target = tmp_path / "out"

  with pytest.raises(SnippetExecError):
    run_builtin(
      "forge/vault/extract",
      tarball_path=str(tarball),
      target_dir=str(target),
    )
