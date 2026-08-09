r"""`forge.toml [imports]` parsing + validation (drain 2026-08-05-0710).

CANONICAL HOME (drain 2026-08-09-2100): forge/forge/core/vault_imports.py.
forge-mcp carries a byte-identical vendored copy at
forge-mcp/src/forge_mcp/vault_imports.py — forge-mcp deliberately does
not depend on the forge package (its deps are mcp/httpx/pydantic only),
so the sharing model is vendoring, same as forge-transpile's
engine_libs and the plugin's engine bundle. Keep the two files
byte-identical; forge-mcp's scripts/check-vault-imports-drift.sh diffs
them and must report clean before either repo ships a change here.

Phase 2 of the vault split. The schema is frozen in
`forge/docs/specs/vault-imports.md` (drain 2026-08-03-1500); this is the
first code to read it.

Phase 2 is LOCAL-PATH ONLY. Nothing here fetches git, resolves a SHA, or
warns about drift — those need a fetch layer that Phase 2b adds. What
this module does is parse the section, validate what can be validated
without a network, and resolve each import to a directory on disk.

ON THE SPEC GAP THIS IMPLEMENTATION FOUND
-----------------------------------------
The spec makes `git` and `sha` REQUIRED and describes `local` as a
developer override layered on top of them. That works for the end state
and does not work for Phase 2: there is no remote for music-core yet, so
a local-only import would have to name a git URL that does not exist and
a SHA that means nothing, purely to satisfy a validator.

So `local` alone is accepted here, and the spec is amended to say so
rather than left to disagree with the code. `git`/`sha` remain required
when `local` is absent — the reproducibility argument for pinning is
untouched; it just does not apply to an import you are pointing at a
directory on your own disk.

The drain prompt uses a `path` key for this. That would be a second
spelling for `local`, so this reads `local` per the spec and rejects
`path` with a message naming the right key.
"""
from __future__ import annotations

try:
  import tomllib
except ImportError:  # Pyodide / <3.11 — same fallback as forge.core.manifest
  import tomli as tomllib
from dataclasses import dataclass
from pathlib import Path

# Reserved: `[[local:note-id]]` names the containing vault, so an import
# called `local` would make that syntax ambiguous — which is the one
# thing it exists to prevent.
RESERVED_IMPORT_NAMES = frozenset({"local"})


class VaultImportError(Exception):
  """A `[imports]` section that cannot be honoured as written."""


@dataclass(frozen=True)
class ImportDecl:
  """One resolved entry from `[imports]`.

  `root` is the directory the import resolves to, already made absolute
  against the importing vault. `sha` and `tag` are carried verbatim and
  unused in Phase 2 — recorded so Phase 2b has them without a re-parse,
  and so a manifest written today does not need rewriting then.
  """

  name: str
  root: Path
  sha: str | None = None
  tag: str | None = None
  git: str | None = None


def parse_imports(forge_toml_path: Path) -> dict[str, ImportDecl]:
  """Read `[imports]` from one `forge.toml`.

  Returns `{}` for a manifest with no `[imports]` section — the common
  case, and not an error.

  Raises `VaultImportError` with an actionable message on anything it
  cannot resolve. Import declarations are configuration a human wrote;
  failing loudly at registration beats a wikilink that mysteriously
  does not resolve three steps later.
  """
  if not forge_toml_path.exists():
    raise VaultImportError(f"No forge.toml at {forge_toml_path}.")

  try:
    manifest = tomllib.loads(forge_toml_path.read_text(encoding="utf-8"))
  except tomllib.TOMLDecodeError as exc:
    raise VaultImportError(
      f"{forge_toml_path} is not valid TOML: {exc}. If you added an "
      "[imports] section, check it is the LAST section in the file — "
      "every key after a [table] header belongs to that table, so an "
      "[imports] header above `name`/`version` swallows them."
    ) from exc

  raw = manifest.get("imports")
  if raw is None:
    return {}
  if not isinstance(raw, dict):
    raise VaultImportError(
      f"{forge_toml_path}: [imports] must be a table of "
      "name = {{ ... }} entries, got {type(raw).__name__}."
    )

  vault_dir = forge_toml_path.parent
  out: dict[str, ImportDecl] = {}
  for name, entry in raw.items():
    out[name] = _parse_one(name, entry, vault_dir, forge_toml_path)
  return out


def _parse_one(
  name: str, entry: object, vault_dir: Path, manifest: Path
) -> ImportDecl:
  where = f"{manifest}: import '{name}'"

  if name in RESERVED_IMPORT_NAMES:
    raise VaultImportError(
      f"{where} uses a reserved name. `[[local:note-id]]` already means "
      "'a note in this vault', so an import called 'local' would make "
      "that form ambiguous."
    )
  if not isinstance(entry, dict):
    raise VaultImportError(
      f"{where} must be a table, e.g. "
      '`music-core = {{ local = "../music-core" }}`.'
    )

  if "path" in entry and "local" not in entry:
    # The one wrong-key case worth naming explicitly, because the drain
    # prompt for this phase used it and somebody will copy that.
    raise VaultImportError(
      f"{where} uses `path`. The key is `local` — see "
      "forge/docs/specs/vault-imports.md."
    )

  local = entry.get("local")
  git = entry.get("git")
  sha = entry.get("sha")

  if local is None:
    if git is None:
      raise VaultImportError(
        f"{where} declares neither `local` nor `git`. Phase 2 resolves "
        'local paths only: `{{ local = "../music-core" }}`.'
      )
    raise VaultImportError(
      f"{where} declares `git` but no `local`. Phase 2 does not fetch "
      "remote imports — add a `local` path pointing at a checkout, or "
      "wait for Phase 2b."
    )

  if not isinstance(local, str) or not local.strip():
    raise VaultImportError(f"{where}: `local` must be a non-empty string.")

  # Relative paths resolve against the IMPORTING vault, not the process
  # cwd — a manifest means the same thing wherever the server runs from.
  root = Path(local).expanduser()
  if not root.is_absolute():
    root = (vault_dir / root).resolve()

  if not root.is_dir():
    raise VaultImportError(
      f"{where} points at {root}, which is not a directory. Relative "
      f"paths resolve against {vault_dir}."
    )

  imported_manifest = root / "forge.toml"
  if not imported_manifest.exists():
    raise VaultImportError(
      f"{where} points at {root}, which has no forge.toml. An imported "
      "vault must be a vault."
    )

  # Name agreement is an error, not a warning: it means the manifest and
  # the thing it points at disagree about what the thing IS, and every
  # later message that says "import 'music-core'" would be lying.
  try:
    declared = tomllib.loads(
      imported_manifest.read_text(encoding="utf-8")
    ).get("name")
  except tomllib.TOMLDecodeError as exc:
    raise VaultImportError(
      f"{where}: {imported_manifest} is not valid TOML: {exc}"
    ) from exc

  if declared != name:
    raise VaultImportError(
      f"{where} resolves to a vault whose forge.toml says "
      f"name = {declared!r}. The import key must match the imported "
      "vault's own name."
    )

  return ImportDecl(name=name, root=root, sha=sha, tag=entry.get("tag"), git=git)


def detect_cycle(
  root_vault: str, edges: dict[str, list[str]]
) -> list[str] | None:
  """Return a cycle through `root_vault` as a path, or None.

  Reports the FULL cycle rather than the edge that closed it — being
  told "music-theory imports music-core imports music-theory" is
  actionable; being told "cycle detected" is not.
  """
  path: list[str] = []
  on_path: set[str] = set()

  def walk(node: str) -> list[str] | None:
    if node in on_path:
      return path[path.index(node):] + [node]
    if node not in edges:
      return None
    path.append(node)
    on_path.add(node)
    for nxt in edges[node]:
      found = walk(nxt)
      if found:
        return found
    path.pop()
    on_path.discard(node)
    return None

  return walk(root_vault)
