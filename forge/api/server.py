import io
import sys
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from forge.core.logic import get_test_value
from forge.core.registry import SnippetRegistry, GraphResolver

app = FastAPI()

app.add_middleware(
  CORSMiddleware,
  allow_origins=["*"],
  allow_methods=["*"],
  allow_headers=["*"],
)

# keyed by absolute vault path
states = {}


class ConnectRequest(BaseModel):
  vault_path: str


class ExecuteRequest(BaseModel):
  vault_path: str
  snippet_id: str
  kwargs: dict = {}


@app.get("/test")
def test():
  return {"result": get_test_value()}


@app.post("/connect")
def connect(req: ConnectRequest):
  if req.vault_path not in states:
    registry = SnippetRegistry()
    registry.scan(req.vault_path)
    states[req.vault_path] = {
      "registry": registry,
      "resolver": GraphResolver(registry),
    }
  return {"status": "connected", "vault_path": req.vault_path}


@app.post("/execute")
def execute(req: ExecuteRequest):
  state = states.get(req.vault_path)
  if state is None:
    raise HTTPException(
      status_code=400, detail="vault not connected — call /connect first")

  snippet = state["resolver"].resolve(req.snippet_id)
  if snippet is None:
    raise HTTPException(
      status_code=404, detail=f"snippet '{req.snippet_id}' not found in vault index")

  meta = snippet["meta"]
  body = snippet["body"]
  snippet_type = meta.get("type")
  if snippet_type == "data":
    props = {k: v for k, v in meta.items() if k not in (
      "type", "title", "description", "inputs")}
    return {"type": "data", "result": props, "stdout": ""}

  if snippet_type == "action":
    code = _extract_python(body)
    if code is None:
      raise HTTPException(
        status_code=422, detail="no '# Python' facet found in snippet")

    stdout, result = _exec_python(code, req.kwargs)
    return {"type": "action", "result": result, "stdout": stdout}

  raise HTTPException(
    status_code=422, detail=f"unknown snippet type: {snippet_type}")


def _extract_python(body):
  lines = body.splitlines()
  collecting = False
  in_fence = False
  code_lines = []
  for line in lines:
    if line.strip() == "# Python":
      collecting = True
      continue
    if not collecting:
      continue
    # stop at any subsequent heading
    if line.startswith("#"):
      break
    # fence opener — enter fence mode and skip the marker line
    if line.strip().startswith("```python"):
      in_fence = True
      continue
    # fence closer — we're done
    if line.strip() == "```":
      if in_fence:
        break
      continue
    # collect the line regardless of fence (handles fenced and unfenced code)
    code_lines.append(line)
  return "\n".join(code_lines).strip() or None


def _exec_python(code, kwargs):
  buf = io.StringIO()
  local_ns = {**kwargs, "kwargs": kwargs}
  old_stdout = sys.stdout
  sys.stdout = buf
  try:
    exec(compile(code, "<snippet>", "exec"), local_ns)
    # if the snippet defines run(context), call it with kwargs
    if callable(local_ns.get("run")):
      result = local_ns["run"](kwargs)
      local_ns["result"] = result
  finally:
    sys.stdout = old_stdout
  return buf.getvalue(), local_ns.get("result")
