from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from forge.core.logic import get_test_value
from forge.core.registry import SnippetRegistry, GraphResolver
from forge.core.executor import extract_python, exec_python, SnippetExecError

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
  kwargs: dict = {}


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
  return {"status": "connected", "vault_path": req.vault_path, "warnings": state["registry"].errors}


@app.post("/execute")
def execute(req: ExecuteRequest, manager: VaultSessionManager = Depends(get_session_manager)):
  state = manager.get(req.vault_path)
  if state is None:
    raise HTTPException(status_code=400, detail="vault not connected — call /connect first")

  snippet = state["resolver"].resolve(req.snippet_id)
  if snippet is None:
    raise HTTPException(status_code=404, detail=f"snippet '{req.snippet_id}' not found in vault index")

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
    try:
      stdout, result = exec_python(code, req.kwargs, state["resolver"])
    except SnippetExecError as e:
      raise HTTPException(status_code=422, detail={"error": str(e), "stdout": e.stdout})
    return {"type": "action", "result": result, "stdout": stdout}

  raise HTTPException(status_code=422, detail=f"unknown snippet type: {snippet_type}")
