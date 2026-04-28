from dotenv import load_dotenv
load_dotenv()

import logging
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from forge.core.logic import get_test_value
from forge.core.registry import SnippetRegistry, GraphResolver
from forge.core.executor import extract_python, exec_python, SnippetExecError, extract_section
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


class ExecuteRequest(BaseModel):
  vault_path: str
  snippet_id: str
  args: list = []
  inputs: dict = {}


class GenerateRequest(BaseModel):
  vault_path: str
  snippet_id: str
  recursive: bool = False


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


@app.post("/execute")
def execute(req: ExecuteRequest, manager: VaultSessionManager = Depends(get_session_manager)):
  state = manager.get(req.vault_path)
  if state is None:
    raise HTTPException(status_code=400, detail="vault not connected — call /connect first")

  try:
    snippet = state["resolver"].resolve(req.snippet_id)
  except SnippetResolutionError as e:
    raise HTTPException(status_code=404, detail=str(e))

  meta = snippet["meta"]
  body = snippet["body"]
  snippet_type = meta.get("type")

  if snippet_type == "data":
    props = {k: v for k, v in meta.items() if k not in ("type", "title", "description", "inputs")}
    return {"type": "data", "result": props, "stdout": ""}

  if snippet_type == "action":
    code = extract_python(body)
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
      )
    except SnippetExecError as e:
      raise HTTPException(status_code=422, detail={"error": str(e), "stdout": e.stdout})
    return {"type": "action", "result": result, "stdout": stdout}

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

  for sid, code in generated.items():
    snippet = state["registry"].get(sid)
    english = extract_section(snippet["body"], "english") if snippet else None
    logger.info("generated [%s]\n  english: %s\n  python:\n%s", sid, english or "(none)", code)

  return {"snippet_id": req.snippet_id, "recursive": req.recursive, "generated": generated}
