from dotenv import load_dotenv
load_dotenv()

import os
import logging
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from forge.core.logic import get_test_value
from forge.core.registry import SnippetRegistry, GraphResolver
from forge.core.executor import extract_python, exec_python, SnippetExecError, extract_section, read_data_snippet
from forge.core.snapshots import set_snapshot_state
from forge.core.dependencies import extract_dependencies, apply_dependencies_to_body
from forge.core.serialization import serialize_result
from forge.core.exceptions import SnippetResolutionError
from forge.core.llm import generate_snippet_code
from forge.builtins.loader import load_builtin_vault

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
_handler = logging.StreamHandler()
_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
logger.addHandler(_handler)

app = FastAPI()

app.add_middleware(
  CORSMiddleware,
  allow_origins=["*"],
  allow_methods=["*"],
  allow_headers=["*"],
)


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
      )
    except SnippetExecError as e:
      raise HTTPException(status_code=422, detail={"error": str(e), "stdout": e.stdout})
    return {"type": "action", "result": serialize_result(result, snippet), "stdout": stdout}

  raise HTTPException(status_code=422, detail=f"unknown snippet type: {snippet_type}")


@app.post("/generate")
def generate(req: GenerateRequest, manager: VaultSessionManager = Depends(get_session_manager)):
  state = manager.get(req.vault_path)
  if state is None:
    raise HTTPException(status_code=400, detail="vault not connected — call /connect first")
  try:
    generated = generate_snippet_code(req.snippet_id, state["registry"], req.recursive)
  except KeyError as e:
    raise HTTPException(status_code=404, detail=str(e))
  except RuntimeError as e:
    raise HTTPException(status_code=500, detail=str(e))

  dependencies = {sid: extract_dependencies(code) for sid, code in generated.items()}

  for sid, code in generated.items():
    snippet = state["registry"].get(sid)
    english = extract_section(snippet["body"], "english") if snippet else None
    logger.info("generated [%s]\n  english: %s\n  python:\n%s", sid, english or "(none)", code)

  return {
    "snippet_id": req.snippet_id,
    "recursive": req.recursive,
    "generated": generated,
    "dependencies": dependencies,
  }


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

  filepath = snippet.get("path")
  if not filepath or not os.path.isfile(filepath):
    # Built-in vault snippets have no on-disk path; we can't write to them.
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
