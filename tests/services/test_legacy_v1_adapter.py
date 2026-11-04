"""Legacy bridge v1 behaviour through the HA service seam with a fake ESPHome client."""

import asyncio
import json
from types import SimpleNamespace

from aioesphomeapi import (
    TextSensorInfo,
    TextSensorState,
    UserService,
    UserServiceArg,
    UserServiceArgType,
)
from homeassistant.core import Context
from homeassistant.exceptions import ServiceValidationError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
import voluptuous as vol

from custom_components.woow_esphome_modbus_scanner.const import DATA_COORDINATOR, DOMAIN
from custom_components.woow_esphome_modbus_scanner.modbus_scan.legacy_v1 import (
    provider as legacy_provider,
)
from custom_components.woow_esphome_modbus_scanner.services import async_register_services

GATEWAY_ID = "esphome:aabbccddeeff"
IN_D17_REGISTERS = [
    0x6201,
    0x6202,
    0x6203,
    0x6205,
    0x6206,
    0x6105,
    0x6101,
    0x6102,
    0x6103,
    0x6104,
    0x6106,
    0x6111,
    0x6112,
]


class FakeLegacyClient:
    """aioesphomeapi client boundary of a node running bridge v1 firmware.

    By default slave 1 responds and every other slave times out; tests subclass it to change
    the replies. Every reply here is FAKE, not hardware acceptance evidence.
    """

    instances: list = []
    outcomes = {1: "responded"}
    probe_action_present = True

    def __init__(self, host, port, password, **kwargs):
        self.probes = []
        self.request_ids = []
        self.closed = False
        FakeLegacyClient.instances.append(self)

    async def connect(self, **kwargs):
        self.on_stop = kwargs["on_stop"]

    async def device_info(self):
        return SimpleNamespace(mac_address="AA:BB:CC:DD:EE:FF")

    async def list_entities_services(self):
        action = UserService(
            name="modbus_scanner_probe_v1",
            key=10,
            args=[
                UserServiceArg("request_id", UserServiceArgType.STRING),
                UserServiceArg("slave", UserServiceArgType.INT),
                UserServiceArg("reg", UserServiceArgType.INT),
            ],
        )
        actions = [action] if self.probe_action_present else []
        return [TextSensorInfo(key=1, name="Modbus Scanner Result")], actions

    def subscribe_states(self, callback):
        self.callback = callback

    def reply(self, data, **changes):
        """Publish a probe result on the result text sensor, correlated unless changed."""
        payload = {
            "v": 1,
            "id": data["request_id"],
            "slave": data["slave"],
            "reg": data["reg"],
            "outcome": self.outcomes.get(data["slave"], "timeout"),
            "latency_ms": 12,
            "value": 1234,
            "exception": 2,
            **changes,
        }
        self.callback(TextSensorState(key=1, state=json.dumps(payload)))

    async def execute_service(self, service, data):
        self.probes.append((data["slave"], data["reg"]))
        self.request_ids.append(data["request_id"])
        self.reply(data)

    async def disconnect(self, force=False):
        self.closed = True


@pytest.fixture(autouse=True)
def fake_client(monkeypatch):
    FakeLegacyClient.instances = []
    monkeypatch.setattr(legacy_provider, "APIClient", FakeLegacyClient)
    return FakeLegacyClient


async def _setup(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, data={"gateways": [{"host": "192.0.2.1", "mac": "AA:BB:CC:DD:EE:FF"}]}
    )
    entry.add_to_hass(hass)
    user = await hass.auth.async_create_user("legacy operator")
    async_register_services(hass, entry.entry_id)
    context = Context(user_id=user.id)

    async def call(service, data=None):
        return await hass.services.async_call(
            DOMAIN, service, data or {}, blocking=True, return_response=True, context=context
        )

    return call


async def test_legacy_gateway_publishes_no_bus_selection_or_scan_lease_support(hass):
    call = await _setup(hass)
    gateway = next(
        g for g in (await call("list_gateways"))["gateways"] if g["gateway_id"] == GATEWAY_ID
    )
    assert gateway["supports_bus_selection"] is False
    assert gateway["supports_scan_lease"] is False


async def test_legacy_gateway_reports_its_limits_in_list_gateways(hass):
    call = await _setup(hass)
    gateway = next(
        g for g in (await call("list_gateways"))["gateways"] if g["gateway_id"] == GATEWAY_ID
    )
    assert gateway["limits"] == {
        "slave_min": 1,
        "slave_max": 32,
        "probe_types": ["holding_register"],
        "register_count_max": 1,
        "allowed_registers": IN_D17_REGISTERS,
        "timeout_ms_min": 700,
        "timeout_ms_max": 700,
        "inter_request_delay_ms_max": 5000,
        "pause_normal_polling_required": True,
        "pause_normal_polling_supported": True,
        "attempt_overhead_ms": 2700,
        # The frozen v1 firmware's defaults (ADR 0004); the panel keeps no copy of them.
        "defaults": {
            "start_id": 1,
            "end_id": 3,
            "address": 1,
            "probe_type": "holding_register",
            "register_address": 0x6201,
            "register_count": 1,
            "timeout_ms": 700,
            "retries": 0,
            "inter_request_delay_ms": 250,
            "pause_normal_polling": True,
        },
    }


async def test_legacy_probe_uses_reported_defaults_and_keeps_result_format(hass):
    call = await _setup(hass)
    started = await call(
        "test_address", {"provider": "esphome", "gateway_id": GATEWAY_ID, "address": 1}
    )
    await asyncio.gather(*hass.data[DOMAIN][DATA_COORDINATOR]._tasks.values())
    assert FakeLegacyClient.instances[0].probes == [(1, 0x6201)]
    # One 700 ms attempt plus the v1 firmware's 2700 ms drain and quiet periods; the budget
    # adds v1 connect, per-attempt API waits and the post-scan polling recovery check.
    assert (started["estimated_worst_case_ms"], started["execution_budget_ms"]) == (3400, 79000)
    results = await call("get_scan_results", {"scan_id": started["scan_id"]})
    assert results["status"] == "completed"
    assert results["responders"] == [
        {
            "address": 1,
            "outcome": "responded",
            "latency_ms": 12,
            "detail": "FC03 register 0x6201 = 1234; CRC validated by ESPHome",
            "register_address": 0x6201,
            "raw_value": 1234,
            "attempts": 1,
        }
    ]


async def test_legacy_gateway_keeps_its_frozen_inter_request_delay_cap(hass):
    """A Legacy Gateway has no Scan Lease, so the bridge v2 3000 ms cap does not apply."""
    call = await _setup(hass)
    started = await call(
        "test_address",
        {"provider": "esphome", "gateway_id": GATEWAY_ID, "address": 1,
         "inter_request_delay_ms": 5000},
    )
    await asyncio.gather(*hass.data[DOMAIN][DATA_COORDINATOR]._tasks.values())
    results = await call("get_scan_results", {"scan_id": started["scan_id"]})
    assert results["status"] == "completed"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"address": 33}, "A Legacy Gateway supports slave IDs 1–32 only"),
        ({"probe_type": "input_register"}, "A Legacy Gateway requires probe_type"),
        ({"register_count": 2}, "A Legacy Gateway requires register_count<=1"),
        (
            {"register_address": 0},
            r"A Legacy Gateway cannot read register 0 \(0x0000\): it is not in the read allowlist",
        ),
        ({"timeout_ms": 500}, "A Legacy Gateway requires timeout_ms=700"),
        ({"pause_normal_polling": False}, "A Legacy Gateway requires pause_normal_polling=true"),
        ({"bus": "rs485"}, "does not support bus selection"),
    ],
)
async def test_service_rejects_requests_outside_legacy_limits_without_bus_traffic(
    hass, changes, message
):
    call = await _setup(hass)
    with pytest.raises(ServiceValidationError, match=message):
        await call(
            "test_address",
            {"provider": "esphome", "gateway_id": GATEWAY_ID, "address": 1, **changes},
        )
    assert FakeLegacyClient.instances == []


async def test_allowlist_rejection_gives_the_frozen_default_register_as_example(hass):
    """The example is the frozen v1 default register (ADR 0004), as in the panel's hint."""
    call = await _setup(hass)
    with pytest.raises(ServiceValidationError, match=r"example: 25089 \(0x6201\)$"):
        await call(
            "test_address",
            {"provider": "esphome", "gateway_id": GATEWAY_ID, "address": 1, "register_address": 0},
        )


PROBE = {"provider": "esphome", "gateway_id": GATEWAY_ID}


def _use(monkeypatch, client_class):
    monkeypatch.setattr(legacy_provider, "APIClient", client_class)


async def _finish(hass):
    await asyncio.gather(
        *hass.data[DOMAIN][DATA_COORDINATOR]._tasks.values(), return_exceptions=True
    )


async def _probe(hass, call, **changes):
    """test_address on the Legacy Gateway; returns its final results."""
    started = await call("test_address", {**PROBE, "address": 1, **changes})
    await _finish(hass)
    return await call("get_scan_results", {"scan_id": started["scan_id"]})


async def test_legacy_scan_ignores_stale_and_uncorrelated_replies(hass, monkeypatch):
    class StaleReplies(FakeLegacyClient):
        async def execute_service(self, service, data):
            self.probes.append((data["slave"], data["reg"]))
            # The initial state subscription and results of other clients' probes (another
            # request id) arrive on the same text sensor; none of them is evidence.
            self.callback(TextSensorState(key=1, state="", missing_state=True))
            self.callback(TextSensorState(key=1, state=""))
            self.reply(data, id="0" * 32, value=9999)
            self.reply(data)

    _use(monkeypatch, StaleReplies)
    call = await _setup(hass)
    results = await _probe(hass, call)
    assert results["status"] == "completed"
    assert [r["raw_value"] for r in results["responders"]] == [1234]


async def test_legacy_reply_for_another_register_fails_the_scan(hass, monkeypatch):
    class WrongRegister(FakeLegacyClient):
        async def execute_service(self, service, data):
            self.probes.append((data["slave"], data["reg"]))
            self.reply(data, reg=0x6202)

    _use(monkeypatch, WrongRegister)
    call = await _setup(hass)
    results = await _probe(hass, call)
    assert results["status"] == "failed"
    assert results["error_info"]["code"] == "RESPONSE_INVALID"
    assert results["responders"] == []
    assert FakeLegacyClient.instances[0].closed


async def test_legacy_connection_loss_is_not_a_slave_timeout(hass, monkeypatch):
    class LostConnection(FakeLegacyClient):
        async def execute_service(self, service, data):
            self.probes.append((data["slave"], data["reg"]))
            await self.on_stop(False)

    _use(monkeypatch, LostConnection)
    call = await _setup(hass)
    results = await _probe(hass, call)
    assert results["status"] == "failed"
    assert results["error_info"]["code"] == "API_DISCONNECTED"
    assert results["outcome_counts"]["timeout"] == 0
    assert FakeLegacyClient.instances[0].closed


async def test_cancelling_a_running_legacy_scan_task_disconnects(hass, monkeypatch):
    """HA shutdown cancels the Scan task while a Probe is still unanswered."""
    sent = asyncio.Event()

    class Unanswered(FakeLegacyClient):
        async def execute_service(self, service, data):
            self.probes.append((data["slave"], data["reg"]))
            sent.set()

    _use(monkeypatch, Unanswered)
    call = await _setup(hass)
    started = await call("test_address", {**PROBE, "address": 1})
    await asyncio.wait_for(sent.wait(), 5)
    hass.data[DOMAIN][DATA_COORDINATOR]._tasks[started["scan_id"]].cancel()
    await _finish(hass)
    status = await call("get_scan_status", {"scan_id": started["scan_id"]})
    assert status["status"] == "cancelled"
    assert FakeLegacyClient.instances[0].closed


async def test_legacy_gateway_without_the_probe_action_is_never_probed(hass, monkeypatch):
    class NoProbeAction(FakeLegacyClient):
        probe_action_present = False

    _use(monkeypatch, NoProbeAction)
    call = await _setup(hass)
    results = await _probe(hass, call)
    assert results["status"] == "failed"
    assert results["error_info"]["code"] == "BRIDGE_UNSUPPORTED"
    assert FakeLegacyClient.instances[0].probes == []
    assert FakeLegacyClient.instances[0].closed


async def test_legacy_timeouts_retry_a_bounded_number_of_times_with_fresh_request_ids(hass):
    call = await _setup(hass)
    results = await _probe(hass, call, address=2, retries=2)
    client = FakeLegacyClient.instances[0]
    assert client.probes == [(2, 0x6201)] * 3
    assert len(set(client.request_ids)) == 3
    assert results["status"] == "completed"
    assert results["outcome_counts"]["timeout"] == 1


async def test_legacy_modbus_exception_is_kept_as_responder_evidence(hass, monkeypatch):
    class ExceptionReply(FakeLegacyClient):
        outcomes = {1: "modbus_exception"}

    _use(monkeypatch, ExceptionReply)
    call = await _setup(hass)
    results = await _probe(hass, call)
    assert [(r["outcome"], r["exception_code"]) for r in results["responders"]] == [
        ("modbus_exception", 2)
    ]


async def test_legacy_gateway_error_fails_the_scan_instead_of_a_timeout(hass, monkeypatch):
    class GatewayError(FakeLegacyClient):
        outcomes = {1: "gateway_error"}

    _use(monkeypatch, GatewayError)
    call = await _setup(hass)
    results = await _probe(hass, call)
    assert results["status"] == "failed"
    assert results["error_info"]["code"] == "FIRMWARE_REJECTED"
    assert results["outcome_counts"]["timeout"] == 0
    assert FakeLegacyClient.instances[0].closed


async def test_legacy_range_scan_probes_exactly_the_requested_ids(hass):
    call = await _setup(hass)
    started = await call(
        "start_scan",
        {
            **PROBE,
            "start_id": 2,
            "end_id": 4,
            "inter_request_delay_ms": 0,
            "safety_confirmed": True,
        },
    )
    await _finish(hass)
    assert FakeLegacyClient.instances[0].probes == [(2, 0x6201), (3, 0x6201), (4, 0x6201)]
    results = await call("get_scan_results", {"scan_id": started["scan_id"]})
    assert (results["status"], results["completed_addresses"]) == ("completed", 3)


async def test_legacy_scan_without_a_range_uses_the_frozen_v1_default_range(hass):
    """The frozen v1 firmware's default range (ADR 0004) is slave IDs 1–3."""
    call = await _setup(hass)
    with pytest.raises(vol.Invalid, match="safety_confirmed"):
        await call("start_scan", PROBE)
    assert FakeLegacyClient.instances == []

    started = await call("start_scan", {**PROBE, "safety_confirmed": True})
    await _finish(hass)
    assert [slave for slave, _reg in FakeLegacyClient.instances[0].probes] == [1, 2, 3]
    results = await call("get_scan_results", {"scan_id": started["scan_id"]})
    assert (results["status"], results["total_addresses"]) == ("completed", 3)


async def test_cancel_scan_before_the_first_probe_sends_nothing(hass, monkeypatch):
    connecting = asyncio.Event()
    release = asyncio.Event()

    class SlowConnect(FakeLegacyClient):
        async def connect(self, **kwargs):
            await super().connect(**kwargs)
            connecting.set()
            await release.wait()

    _use(monkeypatch, SlowConnect)
    call = await _setup(hass)
    started = await call(
        "start_scan", {**PROBE, "start_id": 1, "end_id": 2, "safety_confirmed": True}
    )
    await asyncio.wait_for(connecting.wait(), 5)
    await call("cancel_scan", {"scan_id": started["scan_id"]})
    release.set()
    await _finish(hass)
    status = await call("get_scan_status", {"scan_id": started["scan_id"]})
    assert (status["status"], status["completed_addresses"]) == ("cancelled", 0)
    assert FakeLegacyClient.instances[0].probes == []
    assert FakeLegacyClient.instances[0].closed
