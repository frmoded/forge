import pytest
import responses
import requests
from unittest.mock import patch
from forge.installer.http import get_json, download_to_file, USER_AGENT
from forge.installer.exceptions import (
  HttpError,
  NetworkError,
  TimeoutError,
  ValidationError,
)


@responses.activate
def test_get_json_success():
  responses.add(
    responses.GET,
    "https://example.com/index.json",
    json={"hello": "world"},
    status=200,
  )
  result = get_json("https://example.com/index.json")
  assert result == {"hello": "world"}


@responses.activate
def test_get_json_sends_user_agent():
  responses.add(
    responses.GET,
    "https://example.com/index.json",
    json={},
    status=200,
  )
  get_json("https://example.com/index.json")
  assert responses.calls[0].request.headers["User-Agent"] == USER_AGENT


@responses.activate
def test_get_json_404_raises_http_error():
  responses.add(
    responses.GET,
    "https://example.com/missing",
    status=404,
  )
  with pytest.raises(HttpError) as exc:
    get_json("https://example.com/missing")
  assert exc.value.status_code == 404


@responses.activate
def test_get_json_500_raises_http_error():
  responses.add(
    responses.GET,
    "https://example.com/boom",
    status=500,
  )
  with pytest.raises(HttpError) as exc:
    get_json("https://example.com/boom")
  assert exc.value.status_code == 500


@responses.activate
def test_get_json_malformed_json_raises_validation():
  responses.add(
    responses.GET,
    "https://example.com/index.json",
    body="this is not json",
    status=200,
  )
  with pytest.raises(ValidationError):
    get_json("https://example.com/index.json")


def test_get_json_timeout():
  with patch("forge.installer.http.requests.get", side_effect=requests.exceptions.Timeout()):
    with pytest.raises(TimeoutError):
      get_json("https://example.com/index.json")


def test_get_json_network_error():
  with patch("forge.installer.http.requests.get", side_effect=requests.exceptions.ConnectionError()):
    with pytest.raises(NetworkError):
      get_json("https://example.com/index.json")


@responses.activate
def test_download_to_file_success(tmp_path):
  responses.add(
    responses.GET,
    "https://example.com/file.tar.gz",
    body=b"binary contents",
    status=200,
  )
  dest = tmp_path / "out" / "file.tar.gz"
  download_to_file("https://example.com/file.tar.gz", dest)
  assert dest.read_bytes() == b"binary contents"


@responses.activate
def test_download_to_file_404(tmp_path):
  responses.add(
    responses.GET,
    "https://example.com/missing.tar.gz",
    status=404,
  )
  with pytest.raises(HttpError) as exc:
    download_to_file("https://example.com/missing.tar.gz", tmp_path / "f")
  assert exc.value.status_code == 404


def test_download_timeout(tmp_path):
  with patch("forge.installer.http.requests.get", side_effect=requests.exceptions.Timeout()):
    with pytest.raises(TimeoutError):
      download_to_file("https://example.com/x", tmp_path / "x")
