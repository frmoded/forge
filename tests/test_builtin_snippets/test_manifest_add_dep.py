from pathlib import Path
from forge.core.manifest import Manifest, Dependency, read_manifest


def test_adds_dep_to_existing_manifest(run_builtin, tmp_path):
  vault = tmp_path / "my-vault"
  vault.mkdir()
  (vault / "forge.toml").write_text(
    'name = "my-vault"\nversion = "0.1.0"\ndescription = "An existing vault."\n'
  )

  _, result = run_builtin(
    "forge/manifest/add_dep",
    authoring_vault_dir=str(vault),
    dep_name="forge-core",
    dep_version="0.2.0",
  )

  assert isinstance(result, Manifest)
  assert Dependency(name="forge-core", version="0.2.0") in result.dependencies

  reloaded = read_manifest(vault)
  assert reloaded.dependencies == [Dependency(name="forge-core", version="0.2.0")]


def test_updates_existing_dep_version(run_builtin, tmp_path):
  vault = tmp_path / "my-vault"
  vault.mkdir()
  (vault / "forge.toml").write_text(
    'name = "my-vault"\n'
    'version = "0.1.0"\n'
    'description = "An existing vault."\n'
    '\n[[dependencies]]\nname = "forge-core"\nversion = "0.1.0"\n'
  )

  _, result = run_builtin(
    "forge/manifest/add_dep",
    authoring_vault_dir=str(vault),
    dep_name="forge-core",
    dep_version="0.2.0",
  )
  assert result.dependencies == [Dependency(name="forge-core", version="0.2.0")]


def test_creates_manifest_if_missing(run_builtin, tmp_path):
  vault = tmp_path / "fresh-vault"
  vault.mkdir()

  _, result = run_builtin(
    "forge/manifest/add_dep",
    authoring_vault_dir=str(vault),
    dep_name="forge-core",
    dep_version="0.1.0",
  )

  assert (vault / "forge.toml").is_file()
  reloaded = read_manifest(vault)
  assert reloaded.name == "fresh-vault"
  assert reloaded.version == "0.0.0"
  assert reloaded.description == "Authoring vault."
  assert reloaded.dependencies == [Dependency(name="forge-core", version="0.1.0")]


def test_default_name_sanitizes_basename(run_builtin, tmp_path):
  weird = tmp_path / "My Vault!"
  weird.mkdir()

  _, result = run_builtin(
    "forge/manifest/add_dep",
    authoring_vault_dir=str(weird),
    dep_name="forge-core",
    dep_version="0.1.0",
  )
  assert result.name == "my-vault"


def test_default_name_falls_back_when_unsanitizable(run_builtin, tmp_path):
  # A basename starting with a digit can't satisfy the name regex,
  # so the snippet falls back to the safe default.
  weird = tmp_path / "1"
  weird.mkdir()

  _, result = run_builtin(
    "forge/manifest/add_dep",
    authoring_vault_dir=str(weird),
    dep_name="forge-core",
    dep_version="0.1.0",
  )
  assert result.name == "authoring-vault"


def test_preserves_other_deps(run_builtin, tmp_path):
  vault = tmp_path / "vault-v"
  vault.mkdir()
  (vault / "forge.toml").write_text(
    'name = "vault-v"\nversion = "0.1.0"\ndescription = "x."\n'
    '[[dependencies]]\nname = "alpha"\nversion = "1.0.0"\n'
    '[[dependencies]]\nname = "beta"\nversion = "2.0.0"\n'
  )

  _, result = run_builtin(
    "forge/manifest/add_dep",
    authoring_vault_dir=str(vault),
    dep_name="gamma",
    dep_version="3.0.0",
  )
  names = [d.name for d in result.dependencies]
  assert names == ["alpha", "beta", "gamma"]
