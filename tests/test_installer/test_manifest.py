import shutil
from pathlib import Path
import pytest
from forge.core.manifest import (
  Manifest,
  Dependency,
  read_manifest,
  write_manifest,
  add_or_update_dep,
)
from forge.installer.exceptions import ValidationError

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def vault_dir(tmp_path):
  shutil.copy(FIXTURES / "valid_manifest.toml", tmp_path / "forge.toml")
  return tmp_path


def test_read_valid_manifest(vault_dir):
  m = read_manifest(vault_dir)
  assert m.name == "my-vault"
  assert m.version == "0.1.0"
  assert m.description == "A test vault for unit tests."
  assert len(m.dependencies) == 2
  assert m.dependencies[0] == Dependency(name="forge-core", version="0.1.0")
  assert m.dependencies[1] == Dependency(name="another-vault", version="1.2.3")


def test_read_missing_file(tmp_path):
  with pytest.raises(ValidationError, match="not found"):
    read_manifest(tmp_path)


def test_read_missing_required_field(tmp_path):
  (tmp_path / "forge.toml").write_text('name = "x"\nversion = "0.1.0"\n')
  with pytest.raises(ValidationError, match="description"):
    read_manifest(tmp_path)


def test_read_invalid_name(tmp_path):
  (tmp_path / "forge.toml").write_text(
    'name = "Invalid Name"\nversion = "0.1.0"\ndescription = "x"\n'
  )
  with pytest.raises(ValidationError, match="name"):
    read_manifest(tmp_path)


def test_read_invalid_semver(tmp_path):
  (tmp_path / "forge.toml").write_text(
    'name = "vault-x"\nversion = "not-semver"\ndescription = "x"\n'
  )
  with pytest.raises(ValidationError, match="SemVer"):
    read_manifest(tmp_path)


def test_write_round_trips(vault_dir, tmp_path):
  original = read_manifest(vault_dir)
  out_dir = tmp_path / "copy"
  write_manifest(out_dir, original)
  reloaded = read_manifest(out_dir)
  assert reloaded == original


def test_write_creates_dir(tmp_path):
  out = tmp_path / "fresh" / "vault"
  m = Manifest(name="vault-a", version="0.1.0", description="x")
  write_manifest(out, m)
  assert (out / "forge.toml").is_file()


def test_write_omits_empty_dependencies(tmp_path):
  m = Manifest(name="vault-a", version="0.1.0", description="x")
  write_manifest(tmp_path, m)
  text = (tmp_path / "forge.toml").read_text()
  assert "dependencies" not in text


def test_add_dep_to_empty():
  m = Manifest(name="vault-a", version="0.1.0", description="x")
  updated = add_or_update_dep(m, "forge-core", "0.1.0")
  assert updated.dependencies == [Dependency(name="forge-core", version="0.1.0")]
  # original is unchanged
  assert m.dependencies == []


def test_add_dep_appends_when_new():
  m = Manifest(
    name="vault-a", version="0.1.0", description="x",
    dependencies=[Dependency(name="alpha", version="1.0.0")],
  )
  updated = add_or_update_dep(m, "beta", "2.0.0")
  assert updated.dependencies == [
    Dependency(name="alpha", version="1.0.0"),
    Dependency(name="beta", version="2.0.0"),
  ]


def test_update_dep_preserves_order():
  m = Manifest(
    name="vault-a", version="0.1.0", description="x",
    dependencies=[
      Dependency(name="alpha", version="1.0.0"),
      Dependency(name="beta", version="2.0.0"),
      Dependency(name="gamma", version="3.0.0"),
    ],
  )
  updated = add_or_update_dep(m, "beta", "2.5.0")
  assert updated.dependencies == [
    Dependency(name="alpha", version="1.0.0"),
    Dependency(name="beta", version="2.5.0"),
    Dependency(name="gamma", version="3.0.0"),
  ]


def test_write_validates_invalid_semver(tmp_path):
  m = Manifest(name="vault-a", version="not-semver", description="x")
  with pytest.raises(ValidationError):
    write_manifest(tmp_path, m)
