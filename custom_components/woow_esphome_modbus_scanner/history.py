"""Bounded terminal snapshots. Stored work is NEVER replayed on restart."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import json
from uuid import UUID

from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .modbus_scan.models import ScanOutcome

MAX_RECORDS = 20
MAX_RECORD_BYTES = 128 * 1024


class ScanHistory:
    def __init__(self, hass):
        self.store = Store(hass, 1, f"{DOMAIN}.history")
        self.records = {}
        self.pending = {}
        self.load_error = False

    async def async_load(self):
        try:
            data = await self.store.async_load()
            if data is None:
                return
            if not isinstance(data, dict):
                self.load_error = True
                return
            records = data.get("records", [])
            if not isinstance(records, list):
                self.load_error = True
                return
            for record in records[-MAX_RECORDS:]:
                if self._valid(record):
                    self.records[record["status"]["scan_id"]] = record
                else:
                    self.load_error = True
            pending = data.get("pending", [])
            if isinstance(pending, list):
                for status in pending[-MAX_RECORDS:]:
                    self._interrupt(status)
            while len(self.records) > MAX_RECORDS:
                self.records.pop(next(iter(self.records)))
        except Exception:  # noqa: BLE001 - corrupted history must not disable live gateways
            self.load_error = True

    @staticmethod
    def _valid(record):
        try:
            if not isinstance(record, dict) or set(record) != {"status", "results"}:
                return False
            status, results = record["status"], record["results"]
            scan_id = status["scan_id"]
            events = status.get("events", [])
            phases = {
                "connect",
                "verify_identity",
                "verify_bridge",
                "probe",
                "inter_request_delay",
                "recovery",
                "finished",
                "completed",
                "cancelled",
                "failed",
            }
            if (
                not isinstance(events, list)
                or len(events) > 32
                or any(
                    not isinstance(event, dict)
                    or set(event) != {"phase", "elapsed_ms"}
                    or event.get("phase") not in phases
                    or type(event.get("elapsed_ms")) is not int
                    or event["elapsed_ms"] < 0
                    for event in events
                )
            ):
                return False
            rows = results.get("responders")
            if not isinstance(rows, list) or len(rows) > 247:
                return False
            if any(
                not isinstance(row, dict)
                or type(row.get("address")) is not int
                or not 1 <= row["address"] <= 247
                or row.get("outcome") not in {item.value for item in ScanOutcome}
                for row in rows
            ):
                return False
            return (
                isinstance(status, dict)
                and isinstance(results, dict)
                and str(UUID(scan_id)) == scan_id
                and results["scan_id"] == scan_id
                and status["status"] in {"completed", "cancelled", "failed"}
                and results["status"] == status["status"]
                and status["provider"] in {"mock", "esphome"}
                and results["provider"] == status["provider"]
                and results["gateway_id"] == status["gateway_id"]
                and len(json.dumps(record).encode()) <= MAX_RECORD_BYTES
            )
        except (KeyError, ValueError, TypeError, AttributeError):
            return False

    def _interrupt(self, status):
        """A persisted start is evidence of interruption, never an instruction to run."""
        if not isinstance(status, dict):
            return
        try:
            status = deepcopy(status)
            if status.get("status") != "running" or status.get("scan_id") in self.records:
                return
            status.update(
                status="failed",
                phase="failed",
                finished_at=datetime.now(UTC).isoformat(),
                recovery_status="unknown",
                progress_is_checkpoint=True,
                error=(
                    "HA restarted before a terminal snapshot; progress after the checkpoint "
                    "is unknown. No scan was resumed."
                ),
                error_info={"code": "INTERRUPTED", "phase": "startup", "retryable": False},
            )
            results = {
                key: status[key]
                for key in (
                    "scan_id",
                    "provider",
                    "gateway_id",
                    "status",
                    "phase",
                    "error",
                    "error_info",
                    "completed_addresses",
                    "total_addresses",
                    "outcome_counts",
                )
            }
            results.update(
                responders=[],
                best_effort=True,
                uniqueness_guaranteed=False,
                progress_is_checkpoint=True,
            )
            record = {"status": status, "results": results}
            if self._valid(record):
                self.records[status["scan_id"]] = record
        except (ValueError, KeyError, TypeError):
            self.load_error = True

    def started(self, status):
        self.pending[status["scan_id"]] = deepcopy(status)
        self._schedule_save()

    def _schedule_save(self):
        try:
            self.store.async_delay_save(self._data, 1)
        except Exception:  # noqa: BLE001 - history must not prevent scan cleanup
            self.load_error = True

    def remember(self, status, results):
        record = {"status": deepcopy(status), "results": deepcopy(results)}
        if not self._valid(record):
            self.load_error = True
            return
        self.pending.pop(status["scan_id"], None)
        self.records.pop(status["scan_id"], None)
        self.records[status["scan_id"]] = record
        while len(self.records) > MAX_RECORDS:
            self.records.pop(next(iter(self.records)))
        self._schedule_save()

    def _data(self):
        return {
            "records": list(self.records.values())[-MAX_RECORDS:],
            "pending": list(self.pending.values())[-MAX_RECORDS:],
        }

    def get(self, scan_id):
        record = self.records.get(scan_id)
        return deepcopy(record) if record else None

    def summaries(self):
        return [deepcopy(record["status"]) for record in reversed(list(self.records.values()))]

    async def async_flush(self):
        try:
            await self.store.async_save(self._data())
        except Exception:  # noqa: BLE001 - storage errors don't block safe unloading
            self.load_error = True
