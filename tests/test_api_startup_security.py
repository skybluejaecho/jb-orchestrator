import pytest
from pytest import MonkeyPatch

from jb_orchestrator.api.main import run
from jb_orchestrator.config import get_settings


def test_remote_bind_without_authentication_is_rejected(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("JB_API_HOST", "0.0.0.0")
    monkeypatch.setenv("JB_API_AUTH_ENABLED", "false")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="authentication must be enabled"):
            run()
    finally:
        get_settings.cache_clear()
