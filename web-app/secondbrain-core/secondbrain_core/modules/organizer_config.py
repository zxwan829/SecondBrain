"""Explicit, fail-closed configuration for the optional Organizer model."""
from __future__ import annotations

import os
from collections.abc import Mapping

from .siliconflow_organizer import MODEL_DEFAULT, SiliconFlowOrganizerModel


def configured_organizer_model(environ: Mapping[str, str] | None = None):
    """Load the text adapter only after explicit opt-in; default startup is offline."""
    values = os.environ if environ is None else environ
    enabled = values.get("SB_ORGANIZER_MODEL_ENABLED", "false").strip().lower()
    if enabled not in {"true", "false"}:
        raise RuntimeError("SB_ORGANIZER_MODEL_ENABLED must be true or false")
    if enabled != "true":
        return None

    secret_path = values.get("SB_ORGANIZER_API_KEY_FILE", "").strip()
    if not secret_path:
        raise RuntimeError("Organizer model is enabled but its private API key file is not configured")
    model = values.get("SB_ORGANIZER_MODEL", MODEL_DEFAULT).strip()
    if model != MODEL_DEFAULT:
        raise RuntimeError("Organizer model is not in the locally budgeted model allowlist; no fallback is used")
    return SiliconFlowOrganizerModel.from_secret_file(secret_path, model=model)


def configured_organizer_scheduler(environ: Mapping[str, str] | None = None) -> bool:
    """Scheduler needs its own explicit opt-in; model opt-in alone never starts it."""
    values = os.environ if environ is None else environ
    enabled = values.get("SB_ORGANIZER_SCHEDULER_ENABLED", "false").strip().lower()
    if enabled not in {"true", "false"}:
        raise RuntimeError("SB_ORGANIZER_SCHEDULER_ENABLED must be true or false")
    return enabled == "true"
