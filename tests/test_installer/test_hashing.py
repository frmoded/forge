import hashlib
import pytest
from forge.installer.hashing import sha256_of_file, verify_sha256
from forge.installer.exceptions import HashMismatchError


def test_sha256_known_value(tmp_path):
  path = tmp_path / "input.bin"
  path.write_bytes(b"hello forge")
  expected = hashlib.sha256(b"hello forge").hexdigest()
  assert sha256_of_file(path) == expected


def test_sha256_empty_file(tmp_path):
  path = tmp_path / "empty.bin"
  path.write_bytes(b"")
  # known SHA-256 of the empty string
  assert sha256_of_file(path) == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_sha256_returns_lowercase(tmp_path):
  path = tmp_path / "x"
  path.write_bytes(b"abc")
  digest = sha256_of_file(path)
  assert digest == digest.lower()


def test_verify_sha256_match(tmp_path):
  path = tmp_path / "ok.bin"
  path.write_bytes(b"payload")
  expected = hashlib.sha256(b"payload").hexdigest()
  verify_sha256(path, expected)  # no raise


def test_verify_sha256_mismatch_message_contains_both(tmp_path):
  path = tmp_path / "bad.bin"
  path.write_bytes(b"payload")
  expected = "0" * 64
  with pytest.raises(HashMismatchError) as exc:
    verify_sha256(path, expected)
  msg = str(exc.value)
  assert exc.value.expected == expected
  assert exc.value.actual == hashlib.sha256(b"payload").hexdigest()
  assert exc.value.actual in msg
  assert expected in msg


def test_verify_sha256_case_insensitive(tmp_path):
  path = tmp_path / "x.bin"
  path.write_bytes(b"abc")
  expected = hashlib.sha256(b"abc").hexdigest().upper()
  verify_sha256(path, expected)  # no raise
