"""Immutable active-profile context required by discovery and ranking entry points."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from dashboard.db import get_active_profile


class ProfileApprovalRequired(RuntimeError):
    """Raised when no valid active approved profile can be resolved."""


@dataclass(frozen=True)
class ApprovedProfileContext:
    profile_id: str
    version_id: str
    schema_version: int
    revision: int
    compiled_config: Mapping[str, Any] = field(repr=False)


def get_approved_profile_context(
    *,
    db_path: Path | None = None,
    connection=None,
) -> ApprovedProfileContext:
    """Return the active approved profile or fail before discovery can start.

    Current profile rows were created only after explicit onboarding approval.
    Versioned rows can provide ``active_version_id``, ``schema_version`` and
    ``revision`` after the ordered profile migration lands.
    """
    if connection is None:
        active = get_active_profile(db_path=db_path)
    else:
        row = connection.execute(
            """SELECT p.profile_id, p.active_version_id, v.version_id,
                      v.schema_version, v.revision, v.extracted_json
               FROM profiles AS p
               JOIN profile_versions AS v ON v.version_id = p.active_version_id
               WHERE p.is_active = 1 AND v.status = 'approved'
               ORDER BY p.last_used_at DESC LIMIT 1"""
        ).fetchone()
        active = dict(row) if row else None
    if not active:
        raise ProfileApprovalRequired(
            "Complete onboarding and approve a search profile before discovery."
        )

    try:
        compiled = json.loads(active.get("extracted_json") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ProfileApprovalRequired("The active approved profile is invalid; review and approve it again.") from exc
    if not isinstance(compiled, dict):
        raise ProfileApprovalRequired("The active approved profile is invalid; review and approve it again.")

    profile_id = str(active.get("profile_id") or "").strip()
    if not profile_id:
        raise ProfileApprovalRequired("The active approved profile is invalid; review and approve it again.")

    return ApprovedProfileContext(
        profile_id=profile_id,
        version_id=str(active.get("active_version_id") or active.get("version_id") or profile_id),
        schema_version=int(active.get("schema_version") or 1),
        revision=int(active.get("revision") or 1),
        compiled_config=MappingProxyType(dict(compiled)),
    )
