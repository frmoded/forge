import requests
from forge.core.logic import get_test_value

BASE_URL = "http://127.0.0.1:8000"


class Forge:
  def __init__(self):
    self._vault_path = None

  def connect(self, path, force=False):
    self._vault_path = path
    try:
      resp = requests.post(f"{BASE_URL}/connect",
                           json={"vault_path": path, "force": force}, timeout=2)
      resp.raise_for_status()
      return resp.json()
    except requests.exceptions.ConnectionError:
      return {"status": "offline", "vault_path": path}

  def reload(self):
    if self._vault_path is None:
      raise RuntimeError("call connect() before reload()")
    return self.connect(self._vault_path, force=True)

  def execute(self, snippet_id, *args, **inputs):
    if self._vault_path is None:
      raise RuntimeError("call connect() before execute()")
    resp = requests.post(f"{BASE_URL}/execute", json={
      "vault_path": self._vault_path,
      "snippet_id": snippet_id,
      "args": list(args),
      "inputs": inputs,
    }, timeout=5)
    if not resp.ok:
      try:
        detail = resp.json().get("detail", resp.text)
      except Exception:
        detail = resp.text or resp.reason
      raise RuntimeError(f"execute failed ({resp.status_code}): {detail}")
    return resp.json()

  def generate(self, snippet_id, recursive=False):
    if self._vault_path is None:
      raise RuntimeError("call connect() before generate()")
    resp = requests.post(f"{BASE_URL}/generate", json={
      "vault_path": self._vault_path,
      "snippet_id": snippet_id,
      "recursive": recursive,
    }, timeout=60)
    if not resp.ok:
      try:
        detail = resp.json().get("detail", resp.text)
      except Exception:
        detail = resp.text or resp.reason
      raise RuntimeError(f"generate failed ({resp.status_code}): {detail}")
    return resp.json()

  def test(self):
    try:
      resp = requests.get(f"{BASE_URL}/test", timeout=2)
      return resp.json()["result"]
    except requests.exceptions.ConnectionError:
      return get_test_value()
