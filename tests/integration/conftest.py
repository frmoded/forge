import hashlib
import io
import json
import tarfile
import threading
from collections import Counter
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import pytest

from forge.installer import registry_client


# ---------- registry-cache isolation ----------

@pytest.fixture(autouse=True)
def _clear_registry_cache():
  registry_client.clear_cache()
  yield
  registry_client.clear_cache()


# ---------- relax HTTPS-only check for the local test server ----------

@pytest.fixture(autouse=True)
def _relaxed_scheme_check(monkeypatch):
  real = registry_client.fetch_index

  def _relaxed(url, allow_insecure_schemes=True):
    return real(url, allow_insecure_schemes=allow_insecure_schemes)

  monkeypatch.setattr(registry_client, "fetch_index", _relaxed)


# ---------- tarball + index helpers ----------

def _add_text(tar: tarfile.TarFile, name: str, text: str) -> None:
  data = text.encode("utf-8")
  info = tarfile.TarInfo(name=name)
  info.size = len(data)
  info.mode = 0o644
  tar.addfile(info, io.BytesIO(data))


def pack_tarball(entries, wrapper: str, dest_path: Path) -> str:
  """Build a gzipped tarball where every entry sits under wrapper/.

  entries: iterable of (relative_path, text). Returns the SHA-256 of the result.
  """
  with tarfile.open(dest_path, "w:gz") as tar:
    for rel, content in entries:
      _add_text(tar, f"{wrapper}/{rel}", content)
  return hashlib.sha256(dest_path.read_bytes()).hexdigest()


def build_index(vault_name: str, version: str, tarball_url: str, sha: str) -> dict:
  return {
    "schema_version": "1",
    "vaults": {
      vault_name: {
        "description": f"Test vault {vault_name}",
        "latest": version,
        "versions": {
          version: {"tarball": tarball_url, "sha256": sha},
        },
      }
    },
  }


# ---------- local registry HTTP server ----------

class _LocalServer:
  def __init__(self):
    self._files: dict = {}
    self.request_counts: Counter = Counter()
    self._httpd: HTTPServer = None
    self._thread: threading.Thread = None

  @property
  def url(self) -> str:
    host, port = self._httpd.server_address
    return f"http://{host}:{port}"

  def add_file(self, path: str, body: bytes) -> None:
    if not path.startswith("/"):
      path = "/" + path
    self._files[path] = body

  def add_json(self, path: str, obj: dict) -> None:
    self.add_file(path, json.dumps(obj).encode("utf-8"))

  def _start(self) -> None:
    files = self._files
    counts = self.request_counts

    class Handler(BaseHTTPRequestHandler):
      def log_message(self, *a, **k):
        pass

      def do_GET(self):
        counts[self.path] += 1
        body = files.get(self.path)
        if body is None:
          self.send_response(404)
          self.end_headers()
          return
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    self._httpd = HTTPServer(("127.0.0.1", 0), Handler)
    self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
    self._thread.start()

  def _stop(self) -> None:
    if self._httpd is not None:
      self._httpd.shutdown()
      self._httpd.server_close()
    if self._thread is not None:
      self._thread.join(timeout=2)


@pytest.fixture
def local_registry_server():
  server = _LocalServer()
  server._start()
  try:
    yield server
  finally:
    server._stop()
