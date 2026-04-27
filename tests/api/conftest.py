import pytest
from fastapi.testclient import TestClient
from forge.api.server import app, get_session_manager, VaultSessionManager

_test_manager = VaultSessionManager()


@pytest.fixture(autouse=True)
def reset_manager():
  _test_manager.clear()
  app.dependency_overrides[get_session_manager] = lambda: _test_manager
  yield
  _test_manager.clear()
  app.dependency_overrides.clear()


@pytest.fixture
def client():
  return TestClient(app)
