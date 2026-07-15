"""Static guards for spec 022 — safe-by-default network binding.

The Streamlit surface has no built-in authentication. These tests pin the
safe-by-default posture (loopback bind + XSRF on) and the explicit opt-in seam
(DOCX_AI_BIND_HOST) so a future edit cannot silently re-expose the app on all
interfaces.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.static_workflow


def _streamlit_server_config() -> dict:
    config_path = REPO_ROOT / ".streamlit" / "config.toml"
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    return data.get("server", {})


def test_streamlit_binds_loopback_by_default() -> None:
    server = _streamlit_server_config()
    assert server.get("address") == "127.0.0.1", (
        "Streamlit must bind loopback by default; remote exposure is an explicit "
        "opt-in via DOCX_AI_BIND_HOST."
    )


def test_streamlit_xsrf_protection_enabled() -> None:
    server = _streamlit_server_config()
    assert server.get("enableXsrfProtection") is True


def test_streamlit_cors_not_disabled_while_xsrf_on() -> None:
    # Streamlit force-overrides enableCORS to true when XSRF is on; an explicit
    # enableCORS=false here is a contradiction and a foot-gun.
    server = _streamlit_server_config()
    assert server.get("enableCORS") is not False


def test_shared_ps1_defaults_to_loopback_with_optin_env() -> None:
    text = (REPO_ROOT / "scripts" / "_shared.ps1").read_text(encoding="utf-8")
    # Default host must be loopback; the only way to a non-loopback bind is the
    # documented DOCX_AI_BIND_HOST opt-in.
    assert "DOCX_AI_BIND_HOST" in text
    assert "$serverHost = if ([string]::IsNullOrWhiteSpace($env:DOCX_AI_BIND_HOST))" in text
    # The default must be loopback, never a hard-coded all-interfaces bind.
    # (A doc comment may still mention 0.0.0.0 as the opt-in example.)
    assert "$serverHost = '0.0.0.0'" not in text, (
        "scripts/_shared.ps1 must not hard-default to 0.0.0.0; remote bind is "
        "opt-in via DOCX_AI_BIND_HOST."
    )


def test_start_project_warns_on_non_loopback_bind() -> None:
    text = (REPO_ROOT / "scripts" / "start-project.ps1").read_text(encoding="utf-8")
    assert "Test-IsLoopbackHost" in text
    # A non-loopback bind must surface the no-auth warning before launch.
    assert "reverse proxy" in text.lower()
