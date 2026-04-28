from pathlib import Path
from typing import Any
import json
import requests
from forge.installer.exceptions import (
  HttpError,
  NetworkError,
  TimeoutError,
  ValidationError,
)

USER_AGENT = "Forge/0.1 (+https://github.com/frmoded/forge)"
_HEADERS = {"User-Agent": USER_AGENT}


def get_json(url: str, timeout: float = 10) -> Any:
  try:
    resp = requests.get(url, headers=_HEADERS, timeout=timeout)
  except requests.exceptions.Timeout as e:
    raise TimeoutError(f"GET {url} timed out after {timeout}s") from e
  except requests.exceptions.ConnectionError as e:
    raise NetworkError(f"GET {url} connection failed: {e}") from e
  except requests.exceptions.RequestException as e:
    raise NetworkError(f"GET {url} failed: {e}") from e

  if not resp.ok:
    raise HttpError(f"GET {url} returned {resp.status_code}", status_code=resp.status_code)

  try:
    return resp.json()
  except json.JSONDecodeError as e:
    raise ValidationError(f"GET {url} returned non-JSON body: {e}") from e


def download_to_file(url: str, dest_path: Path, timeout: float = 30) -> None:
  try:
    resp = requests.get(url, headers=_HEADERS, timeout=timeout, stream=True)
  except requests.exceptions.Timeout as e:
    raise TimeoutError(f"GET {url} timed out after {timeout}s") from e
  except requests.exceptions.ConnectionError as e:
    raise NetworkError(f"GET {url} connection failed: {e}") from e
  except requests.exceptions.RequestException as e:
    raise NetworkError(f"GET {url} failed: {e}") from e

  if not resp.ok:
    raise HttpError(f"GET {url} returned {resp.status_code}", status_code=resp.status_code)

  dest_path.parent.mkdir(parents=True, exist_ok=True)
  with open(dest_path, "wb") as f:
    for chunk in resp.iter_content(chunk_size=64 * 1024):
      if chunk:
        f.write(chunk)
