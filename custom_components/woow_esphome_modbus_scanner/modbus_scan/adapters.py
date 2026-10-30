"""Registration point for physical gateway provider adapters."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def build_physical_provider(gateways: Sequence[dict[str, Any]]):
    """Return the provider serving the enrolled physical gateways, if any."""
    if not gateways:
        return None
    # Legacy bridge v1 registration: delete these two lines with ``legacy_v1/``.
    from .legacy_v1 import build_provider as build_legacy_v1_provider

    return build_legacy_v1_provider(gateways)
