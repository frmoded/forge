import io
import tarfile
from pathlib import Path
import pytest


def _add_text(tar: tarfile.TarFile, name: str, content: str) -> None:
  data = content.encode("utf-8")
  info = tarfile.TarInfo(name=name)
  info.size = len(data)
  info.mode = 0o644
  tar.addfile(info, io.BytesIO(data))


@pytest.fixture
def make_tarball(tmp_path):
  """Builds a .tar.gz programmatically. entries: list of (path, content)."""
  def _make(name: str, entries):
    path = tmp_path / name
    with tarfile.open(path, "w:gz") as tar:
      for entry_name, content in entries:
        _add_text(tar, entry_name, content)
    return path
  return _make


@pytest.fixture
def valid_wrapped_tarball(make_tarball):
  """Mimics GitHub's archive layout: wrapper dir over the actual content."""
  return make_tarball("wrapped.tar.gz", [
    ("forge-core-0.1.0/forge.toml", 'name = "forge-core"\n'),
    ("forge-core-0.1.0/snippets/hello.md", "hello\n"),
    ("forge-core-0.1.0/snippets/nested/x.md", "nested\n"),
  ])


@pytest.fixture
def traversal_tarball(make_tarball):
  return make_tarball("traversal.tar.gz", [
    ("forge-core-0.1.0/forge.toml", "ok\n"),
    ("forge-core-0.1.0/../escape.md", "evil\n"),
  ])


@pytest.fixture
def absolute_path_tarball(make_tarball):
  return make_tarball("absolute.tar.gz", [
    ("forge-core-0.1.0/forge.toml", "ok\n"),
    ("/etc/passwd-evil", "evil\n"),
  ])
