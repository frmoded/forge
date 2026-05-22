from dotenv import load_dotenv
load_dotenv()

import os
import logging
import time
from fastapi import FastAPI, Depends, HTTPException, Request
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from forge.core.logic import get_test_value
from forge.core.registry import SnippetRegistry, GraphResolver
from forge.core.executor import extract_python, exec_python, SnippetExecError, read_data_snippet
from forge.core.snapshots import set_snapshot_state
from forge.core.dependencies import extract_dependencies, apply_dependencies_to_body
from forge.core.serialization import serialize_result, SUPPORTED_CONTENT_TYPES
from forge.core.exceptions import SnippetResolutionError
from forge.core.llm import generate_snippet_code, canonicalize_python
from forge.core.manifest import read_manifest

_log = logging.getLogger(__name__)


def _read_vault_domains(vault_path):
  """Active domain scope for a vault (constitution B9 / domain-scoping).

  Returns the manifest's `domains` list, or None if the field is
  absent / the manifest can't be read — None means "all registered
  domains" (back-compat for vaults authored before the field). A
  one-line warning is logged on the back-compat path so authors know
  to declare `domains` in forge.toml.
  """
  try:
    domains = read_manifest(vault_path).domains
  except Exception as e:  # missing/malformed forge.toml — stay permissive
    _log.warning(
      "forge.toml unreadable for %s (%s); treating as all-domains "
      "(declare `domains = [...]` to scope)", vault_path, e)
    return None
  if domains is None:
    _log.warning(
      "vault %s declares no `domains` in forge.toml; treating as "
      "all-domains (back-compat — declare `domains = [...]` to scope)",
      vault_path)
  return domains
from forge.builtins.loader import load_builtin_vault
from forge.api.moda import router as moda_router

# Attach the handler to the package-root logger so every forge.* submodule
# (forge.core.llm, forge.api.server, ...) inherits it via propagation.
_forge_logger = logging.getLogger("forge")
_forge_logger.setLevel(logging.INFO)
if not _forge_logger.handlers:
  _handler = logging.StreamHandler()
  _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
  _forge_logger.addHandler(_handler)

logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
  CORSMiddleware,
  allow_origins=["*"],
  allow_methods=["*"],
  allow_headers=["*"],
)

app.include_router(moda_router)


@app.middleware("http")
async def log_request_time(request: Request, call_next):
  start = time.perf_counter()
  response = await call_next(request)
  elapsed_ms = (time.perf_counter() - start) * 1000
  logger.info("%s %s -> %s (%.0fms)", request.method, request.url.path, response.status_code, elapsed_ms)
  return response


class VaultSessionManager:
  def __init__(self):
    self._states = {}

  def connect(self, vault_path):
    if vault_path not in self._states:
      self._load(vault_path)

  def reload(self, vault_path):
    self._load(vault_path)

  def _load(self, vault_path):
    registry = SnippetRegistry()
    registry.scan(vault_path)
    registry.register_builtin_vault(load_builtin_vault())
    self._states[vault_path] = {
      "registry": registry,
      "resolver": GraphResolver(registry),
      "domains": _read_vault_domains(vault_path),
    }

  def get(self, vault_path):
    return self._states.get(vault_path)

  def clear(self):
    self._states.clear()


_manager = VaultSessionManager()


def get_session_manager() -> VaultSessionManager:
  return _manager


class ConnectRequest(BaseModel):
  vault_path: str
  force: bool = False


class ComputeRequest(BaseModel):
  vault_path: str
  snippet_id: str
  args: list = []
  inputs: dict = {}


class GenerateRequest(BaseModel):
  vault_path: str
  snippet_id: str
  recursive: bool = False


class FreezeRequest(BaseModel):
  vault_path: str
  caller: str
  callee: str
  state: str


class SyncDependenciesRequest(BaseModel):
  vault_path: str
  snippet_id: str


class CanonicalizeRequest(BaseModel):
  vault_path: str
  snippet_id: str


@app.get("/test")
def test():
  return {"result": get_test_value()}


@app.post("/connect")
def connect(req: ConnectRequest, manager: VaultSessionManager = Depends(get_session_manager)):
  if req.force:
    manager.reload(req.vault_path)
  else:
    manager.connect(req.vault_path)
  state = manager.get(req.vault_path)
  return {
    "status": "connected",
    "vault_path": req.vault_path,
    "warnings": state["registry"].errors,
    "snippets": state["registry"].list_snippets(),
    "content_types": list(SUPPORTED_CONTENT_TYPES),
  }


@app.post("/compute")
def compute(req: ComputeRequest, manager: VaultSessionManager = Depends(get_session_manager)):
  state = manager.get(req.vault_path)
  if state is None:
    raise HTTPException(status_code=400, detail="vault not connected — call /connect first")

  try:
    snippet = state["resolver"].resolve(req.snippet_id)
  except SnippetResolutionError as e:
    raise HTTPException(status_code=404, detail=str(e))

  snippet_type = snippet["meta"].get("type")

  if snippet_type in ("data", "snapshot"):
    try:
      value = read_data_snippet(snippet)
    except (ValueError, KeyError) as e:
      raise HTTPException(status_code=422, detail={"error": str(e), "stdout": ""})
    return {"type": snippet_type, "result": serialize_result(value, snippet), "stdout": ""}

  if snippet_type == "action":
    code = extract_python(snippet["body"])
    if code is None:
      raise HTTPException(status_code=422, detail="no Python heading found in snippet")
    trusted = snippet.get("source") == "builtin"
    try:
      stdout, result = exec_python(
        code, req.inputs, state["resolver"],
        args=req.args,
        vault_path=req.vault_path,
        registry=state["registry"],
        trusted=trusted,
        snippet_id=snippet["snippet_id"],
        domains=state.get("domains"),
      )
    except SnippetExecError as e:
      raise HTTPException(status_code=422, detail={"error": str(e), "stdout": e.stdout})
    return {"type": "action", "result": serialize_result(result, snippet), "stdout": stdout}

  raise HTTPException(status_code=422, detail=f"unknown snippet type: {snippet_type}")


def _translate_anthropic_error(exc):
  """Map an anthropic SDK exception to the (status, detail) pair the
  /generate and /canonicalize handlers surface to the plugin.

  We split Anthropic-side failures into two buckets:
    * **Retryable** (503): transient — overloaded, rate-limited,
      connection/timeout, upstream 5xx. Same call again later likely
      works.
    * **Non-retryable** (502): authentication, billing, permission,
      bad-request style errors. The user has to fix something
      (API key, prompt content, etc.) before retrying.

  Detail body shape:
      {"error": "<human-readable>", "retryable": true|false,
       "upstream_status": <int|None>, "kind": "<sdk_exception_name>"}

  The plugin reads `retryable` to decide whether to show a "try
  again in a moment" Notice (and, in a future revision, auto-retry
  with backoff). `kind` is for diagnostics; the plugin doesn't
  branch on it but a developer reading the console can see exactly
  which SDK class fired.

  Anthropic's `APIStatusError` carries the upstream HTTP status on
  `.status_code`; connection / timeout errors have no upstream
  status so the field is None.
  """
  from anthropic import APIError, APIStatusError
  if not isinstance(exc, APIError):
    return None
  upstream_status = getattr(exc, "status_code", None)
  retryable = (
    upstream_status is None  # connection / timeout — always retryable
    or upstream_status == 429  # rate-limited
    or upstream_status >= 500  # upstream 5xx (overloaded, internal)
  )
  http_status = 503 if retryable else 502
  detail = {
    "error": f"Anthropic API: {exc}",
    "retryable": retryable,
    "upstream_status": upstream_status,
    "kind": type(exc).__name__,
  }
  return (http_status, detail)


@app.post("/generate")
def generate(req: GenerateRequest, manager: VaultSessionManager = Depends(get_session_manager)):
  from anthropic import APIError
  state = manager.get(req.vault_path)
  if state is None:
    raise HTTPException(status_code=400, detail="vault not connected — call /connect first")
  try:
    generated = generate_snippet_code(
      req.snippet_id, state["registry"], req.recursive,
      active_domains=state.get("domains"),
    )
  except KeyError as e:
    raise HTTPException(status_code=404, detail=str(e))
  except APIError as e:
    status, detail = _translate_anthropic_error(e)
    raise HTTPException(status_code=status, detail=detail)
  except RuntimeError as e:
    raise HTTPException(status_code=500, detail=str(e))

  dependencies = {sid: extract_dependencies(code) for sid, code in generated.items()}

  return {
    "snippet_id": req.snippet_id,
    "recursive": req.recursive,
    "generated": generated,
    "dependencies": dependencies,
  }


@app.post("/canonicalize")
def canonicalize(req: CanonicalizeRequest, manager: VaultSessionManager = Depends(get_session_manager)):
  """Reverse direction of /generate: given a snippet whose Python facet has
  been hand-tuned, ask the LLM for a canonical English description and
  return it. The plugin writes the response back to the snippet's
  `# English` section. Stateless on the server; no file write here."""
  state = manager.get(req.vault_path)
  if state is None:
    raise HTTPException(status_code=400, detail="vault not connected — call /connect first")
  from anthropic import APIError
  try:
    english = canonicalize_python(
      req.snippet_id, state["registry"],
      active_domains=state.get("domains"),
    )
  except KeyError as e:
    raise HTTPException(status_code=404, detail=str(e))
  except ValueError as e:
    raise HTTPException(status_code=422, detail=str(e))
  except APIError as e:
    status, detail = _translate_anthropic_error(e)
    raise HTTPException(status_code=status, detail=detail)
  except RuntimeError as e:
    raise HTTPException(status_code=500, detail=str(e))
  return {"snippet_id": req.snippet_id, "english": english}


@app.post("/sync_dependencies")
def sync_dependencies(req: SyncDependenciesRequest, manager: VaultSessionManager = Depends(get_session_manager)):
  """Re-sync the # Dependencies section of a snippet to whatever its current
  Python facet calls. Distinct from /generate — no LLM, no Python rewrite."""
  state = manager.get(req.vault_path)
  if state is None:
    raise HTTPException(status_code=400, detail="vault not connected — call /connect first")

  try:
    snippet = state["resolver"].resolve(req.snippet_id)
  except SnippetResolutionError as e:
    raise HTTPException(status_code=404, detail=str(e))

  if snippet.get("source") == "builtin":
    # Builtin snippets DO have on-disk paths inside the forge package, so the
    # filepath check below isn't enough — block them explicitly. Letting
    # /sync_dependencies write here would leak per-user state into the
    # shipped package (and was how install.md grew a stale # Dependencies
    # block during pre-fix Forge-on-install runs).
    raise HTTPException(
      status_code=422,
      detail=f"snippet '{req.snippet_id}' is a builtin and is not writable",
    )

  filepath = snippet.get("path")
  if not filepath or not os.path.isfile(filepath):
    raise HTTPException(status_code=422, detail=f"snippet '{req.snippet_id}' has no writable filesystem path")

  with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

  # Split frontmatter from body so we can rewrite the body in place.
  if not content.startswith("---"):
    raise HTTPException(status_code=422, detail=f"snippet '{req.snippet_id}' has no frontmatter")
  parts = content.split("---", 2)
  if len(parts) < 3:
    raise HTTPException(status_code=422, detail=f"snippet '{req.snippet_id}' frontmatter is malformed")
  frontmatter = f"---{parts[1]}---"
  body = parts[2].lstrip("\n")

  python = extract_python(body)
  if python is None:
    raise HTTPException(status_code=422, detail=f"snippet '{req.snippet_id}' has no Python facet")

  deps = extract_dependencies(python)
  new_body = apply_dependencies_to_body(body, deps)

  with open(filepath, "w", encoding="utf-8") as f:
    f.write(f"{frontmatter}\n\n{new_body}")

  return {"snippet_id": req.snippet_id, "dependencies": deps}


@app.post("/freeze")
def freeze(req: FreezeRequest):
  if req.state not in ("frozen", "live"):
    raise HTTPException(status_code=422, detail=f"state must be 'frozen' or 'live', got {req.state!r}")
  try:
    set_snapshot_state(req.vault_path, req.caller, req.callee, req.state)
  except FileNotFoundError:
    raise HTTPException(
      status_code=404,
      detail=f"no snapshot for edge {req.caller!r} -> {req.callee!r} (the edge has never been traversed)",
    )
  return {"caller": req.caller, "callee": req.callee, "state": req.state}
