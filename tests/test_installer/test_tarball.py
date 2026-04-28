import pytest
from forge.installer.tarball import extract_tarball
from forge.installer.exceptions import PathTraversalError


def test_extract_strips_wrapper(valid_wrapped_tarball, tmp_path):
  target = tmp_path / "out"
  root = extract_tarball(valid_wrapped_tarball, target)
  assert root == target
  assert (target / "forge.toml").is_file()
  assert (target / "snippets" / "hello.md").is_file()
  assert (target / "snippets" / "nested" / "x.md").is_file()
  # the wrapper dir itself is gone
  assert not (target / "forge-core-0.1.0").exists()


def test_extract_creates_target_if_missing(valid_wrapped_tarball, tmp_path):
  target = tmp_path / "fresh" / "out"
  assert not target.exists()
  extract_tarball(valid_wrapped_tarball, target)
  assert target.is_dir()


def test_rejects_path_traversal(traversal_tarball, tmp_path):
  with pytest.raises(PathTraversalError):
    extract_tarball(traversal_tarball, tmp_path / "out")


def test_rejects_absolute_paths(absolute_path_tarball, tmp_path):
  with pytest.raises(PathTraversalError):
    extract_tarball(absolute_path_tarball, tmp_path / "out")


def test_aborts_before_writing_anything(traversal_tarball, tmp_path):
  target = tmp_path / "out"
  with pytest.raises(PathTraversalError):
    extract_tarball(traversal_tarball, target)
  # the safe entry was never extracted because validation runs up front
  assert not (target / "forge.toml").exists()


def test_strip_zero_keeps_wrapper(valid_wrapped_tarball, tmp_path):
  target = tmp_path / "out"
  extract_tarball(valid_wrapped_tarball, target, strip_components=0)
  assert (target / "forge-core-0.1.0" / "forge.toml").is_file()


def test_strip_two_drops_two_levels(make_tarball, tmp_path):
  tarball = make_tarball("deep.tar.gz", [
    ("a/b/file.md", "x"),
  ])
  target = tmp_path / "out"
  extract_tarball(tarball, target, strip_components=2)
  assert (target / "file.md").is_file()
