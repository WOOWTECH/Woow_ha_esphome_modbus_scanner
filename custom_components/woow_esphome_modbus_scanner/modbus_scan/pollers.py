"""Which Pausable Pollers a Scan pauses: a saved checklist revalidated against the firmware.

A checklist row is ``{"index", "name", "address", "paused"}``. A row matches a poller of the
firmware table only when index, name and address are all equal, so a renumbered or renamed
poller after a recompile is never paused on the strength of an old choice.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

POLLER_KEYS = ("index", "name", "address")


def _identity(poller: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(poller.get(key) for key in POLLER_KEYS)


def _poller(poller: dict[str, Any]) -> dict[str, Any]:
    return {key: poller[key] for key in POLLER_KEYS}


def reconcile(
    table: Sequence[dict[str, Any]], saved: Iterable[dict[str, Any]] | None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(checklist for the firmware table, saved rows no longer in it).

    Pollers without a saved row (all of them when nothing is saved) are paused: pausing is
    the safe default.
    """
    saved = list(saved or ())
    choices = {_identity(row): row.get("paused") is not False for row in saved}
    checklist = [{**_poller(p), "paused": choices.get(_identity(p), True)} for p in table]
    current = {_identity(p) for p in table}
    removed = [_poller(row) for row in saved if _identity(row) not in current]
    return checklist, removed


def choose(
    table: Sequence[dict[str, Any]], indices: Iterable[int]
) -> tuple[list[dict[str, Any]], list[int]]:
    """(checklist pausing exactly ``indices``, requested indices not in the table)."""
    wanted = set(indices)
    known = {p["index"] for p in table}
    checklist = [{**_poller(p), "paused": p["index"] in wanted} for p in table]
    return checklist, sorted(wanted - known)


def paused_pollers(checklist: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """The pollers a checklist pauses."""
    return [_poller(row) for row in checklist if row["paused"]]
