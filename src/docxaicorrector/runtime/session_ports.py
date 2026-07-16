"""UI-free session-token ports (F3).

Holds the Streamlit-free session-token accessors the ``processing`` core needs so
importing that core never transitively loads Streamlit. This module MUST NOT
import ``streamlit`` at module level. ``st.session_state`` is only used as the
DEFAULT when a caller does not inject a ``session_state``; that default is
resolved via a LAZY ``import streamlit`` INSIDE ``_resolve_session_state`` so that
importing this module — and any headless caller that passes an explicit
``session_state`` — never loads Streamlit.

``runtime.state`` re-exports these names for backward compatibility.
"""

from __future__ import annotations

from typing import Any


def _resolve_session_state(session_state: Any = None) -> Any:
    if session_state is not None:
        return session_state
    import streamlit as st

    return st.session_state


def get_selected_source_token(*, session_state: Any = None) -> str:
    resolved_session_state = _resolve_session_state(session_state)
    return str(resolved_session_state.get("selected_source_token", ""))


def set_selected_source_token(uploaded_token: str, *, session_state: Any = None) -> None:
    _resolve_session_state(session_state).selected_source_token = uploaded_token
