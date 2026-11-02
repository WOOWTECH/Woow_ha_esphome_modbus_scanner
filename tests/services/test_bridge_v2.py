"""Bridge v2 Probes through the HA service seam, with a fake v2 Gateway at the API boundary.

The fake Gateway is built from the shared protocol contract file, the same file the
host-compiled firmware tests read, so protocol drift fails on both sides.
"""

import asyncio
import json
from pathlib import Path
import re
from types import SimpleNamespace

from aioesphomeapi import (
    TextSensorInfo,
    TextSensorState,
    UserService,
    UserServiceArg,
    UserServiceArgType,
)
from homeassistant.core import Context
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.woow_esphome_modbus_scanner.const import DATA_COORDINATOR, DOMAIN
from custom_components.woow_esphome_modbus_scanner.modbus_scan.bridge_v2 import (
    provider as v2_provider,
)
from custom_components.woow_esphome_modbus_scanner.services import async_register_services

CONTRACT = json.loads(
    (
        Path(__file__).parents[2]
        / "custom_components/woow_esphome_modbus_scanner/modbus_scan/bridge_v2/contract.json"
    ).read_text(encoding="utf-8")
)
MAC = "AA:BB:CC:DD:EE:01"
GATEWAY_ID = "esphome:aabbccddee01"
ARG_TYPES = {"string": UserServiceArgType.STRING, "int": UserServiceArgType.INT}
INFO_KEY, RESULT_KEY = 1, 2


class FakeV2Gateway:
    """A node running the modbus_scanner component, speaking bridge v2 per the contract.

    ``devices`` maps (bus, slave) to a responder: a list of register values, or an int
    Modbus exception code. Anything else times out, like a silent RS-485 address.
    """

    def __init__(self, *, mac=MAC, buses=("rs485",), devices=None):
        self.mac = mac
        self.buses = list(buses)
        self.devices = devices or {}
        self.probes = []
        self.result_override = None
        self.services = [
            UserService(
                name=CONTRACT["actions"]["probe"]["name"],
                key=10,
                args=[
                    UserServiceArg(arg["name"], ARG_TYPES[arg["type"]])
                    for arg in CONTRACT["actions"]["probe"]["args"]
                ],
            )
        ]
        self.entities = [
            TextSensorInfo(key=INFO_KEY, name=CONTRACT["text_sensors"]["info"]["name"]),
            TextSensorInfo(key=RESULT_KEY, name=CONTRACT["text_sensors"]["result"]["name"]),
        ]

    def info(self):
        return {
            "v": CONTRACT["info"]["schema_version"],
            "bridge": CONTRACT["bridge_version"],
            "buses": [{"bus": bus, "pollers": []} for bus in self.buses],
        }

    def _rejection(self, data):
        limits = CONTRACT["hard_limits"]
        ident = CONTRACT["identifiers"]["request_id"]
        if not re.fullmatch(
            f"[{ident['charset']}]{{{ident['min_length']},{ident['max_length']}}}",
            data["request_id"],
        ):
            return "invalid_request_id"
        if data["function_code"] in limits["write_function_codes"]:
            return "write_function_refused"
        if data["bus"] not in self.buses:
            return "unknown_bus"
        if not limits["slave_min"] <= data["slave"] <= limits["slave_max"]:
            return "invalid_slave"
        if data["function_code"] not in limits["function_codes"]:
            return "unsupported_function_code"
        if not limits["count_min"] <= data["count"] <= limits["count_max"]:
            return "invalid_count"
        if not limits["timeout_ms_min"] <= data["timeout_ms"] <= limits["timeout_ms_max"]:
            return "invalid_timeout"
        if data["pause_pollers"] != "":
            return "invalid_poller"
        return None

    def execute(self, data):
        """Firmware behaviour: one result per probe, published on the result sensor."""
        self.probes.append(dict(data))
        if self.result_override is not None:
            return self.result_override(data)
        return self.firmware_result(data)

    def firmware_result(self, data):
        result = {
            "v": CONTRACT["result"]["schema_version"],
            "id": data["request_id"],
            "bus": data["bus"],
            "slave": data["slave"],
            "fc": data["function_code"],
            "reg": data["register"],
            "count": data["count"],
            "latency_ms": 0,
        }
        if error := self._rejection(data):
            return {**result, "outcome": "gateway_error", "error": error}
        device = self.devices.get((data["bus"], data["slave"]))
        if isinstance(device, list):
            return {**result, "outcome": "responded", "latency_ms": 18, "values": device}
        if isinstance(device, int):
            return {**result, "outcome": "modbus_exception", "latency_ms": 9, "exception": device}
        return {**result, "outcome": "timeout", "latency_ms": data["timeout_ms"]}


class FakeClient:
    """aioesphomeapi APIClient boundary in front of a FakeV2Gateway."""

    gateway: FakeV2Gateway
    instances: list = []

    def __init__(self, host, port, password, **kwargs):
        self.host = host
        self.connected = False
        FakeClient.instances.append(self)

    async def connect(self, **kwargs):
        self.connected = True

    async def device_info(self):
        return SimpleNamespace(mac_address=self.gateway.mac)

    async def list_entities_services(self):
        return list(self.gateway.entities), list(self.gateway.services)

    def subscribe_states(self, callback):
        self.callback = callback
        callback(TextSensorState(key=INFO_KEY, state=json.dumps(self.gateway.info())))

    def execute_service(self, service, data):
        result = self.gateway.execute(data)
        if result is not None:
            self.callback(
                TextSensorState(key=RESULT_KEY, state=json.dumps(result, separators=(",", ":")))
            )

    async def disconnect(self, force=False):
        self.connected = False


@pytest.fixture
def gateway(monkeypatch):
    node = FakeV2Gateway(devices={("rs485", 7): [1234, 65535], ("rs485", 9): 2})
    FakeClient.gateway = node
    FakeClient.instances = []
    monkeypatch.setattr(v2_provider, "APIClient", FakeClient)
    return node


async def _setup(hass, *, mac=MAC):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"gateways": [{"host": "192.0.2.10", "mac": mac, "bridge": "v2"}]},
    )
    entry.add_to_hass(hass)
    user = await hass.auth.async_create_user("v2 operator")
    async_register_services(hass, entry.entry_id)
    context = Context(user_id=user.id)

    async def call(service, data=None):
        return await hass.services.async_call(
            DOMAIN, service, data or {}, blocking=True, return_response=True, context=context
        )

    return call


async def _settle(hass):
    await asyncio.gather(*hass.data[DOMAIN][DATA_COORDINATOR]._tasks.values())


async def _test_address(hass, call, **fields):
    started = await call(
        "test_address", {"provider": "esphome", "gateway_id": GATEWAY_ID, **fields}
    )
    await _settle(hass)
    return await call("get_scan_results", {"scan_id": started["scan_id"]})


async def test_test_address_reads_raw_registers_from_a_v2_gateway(hass, gateway):
    call = await _setup(hass)

    results = await _test_address(
        hass,
        call,
        address=7,
        probe_type="input_register",
        register_address=0x0100,
        register_count=2,
        timeout_ms=300,
    )

    assert results["status"] == "completed"
    assert results["responders"] == [
        {
            "address": 7,
            "outcome": "responded",
            "latency_ms": 18,
            "detail": "FC04 register 0x0100 x2 = [1234, 65535]",
            "register_address": 0x0100,
            "raw_value": 1234,
            "raw_values": [1234, 65535],
            "attempts": 1,
        }
    ]
    [probe] = gateway.probes
    assert {k: v for k, v in probe.items() if k not in ("request_id", "scan_id")} == {
        "bus": "rs485",
        "slave": 7,
        "function_code": 4,
        "register": 0x0100,
        "count": 2,
        "timeout_ms": 300,
        "pause_pollers": "",
    }


async def test_v2_gateway_reports_contract_hard_limits_in_list_gateways(hass, gateway):
    call = await _setup(hass)
    listed = next(
        g for g in (await call("list_gateways"))["gateways"] if g["gateway_id"] == GATEWAY_ID
    )
    assert "bridge_v2" in listed["capabilities"]
    assert listed["limits"] == {
        "slave_min": 1,
        "slave_max": 247,
        "probe_types": ["holding_register", "input_register"],
        "register_count_max": 4,
        "allowed_registers": None,
        "timeout_ms_min": 100,
        "timeout_ms_max": 2000,
        "pause_normal_polling_required": False,
        "pause_normal_polling_supported": False,
    }


async def test_timeouts_are_counted_but_exceptions_are_listed(hass, gateway):
    call = await _setup(hass)
    timed_out = await _test_address(hass, call, address=200)
    assert timed_out["outcome_counts"]["timeout"] == 1
    assert timed_out["responders"] == []

    excepted = await _test_address(hass, call, address=9)
    [row] = excepted["responders"]
    assert (row["outcome"], row["exception_code"]) == ("modbus_exception", 2)


async def test_default_probe_is_fc03_single_register_without_pausing(hass, gateway):
    call = await _setup(hass)
    await _test_address(hass, call, address=200)
    [probe] = gateway.probes
    assert (probe["function_code"], probe["count"], probe["pause_pollers"]) == (3, 1, "")


async def test_mac_mismatch_fails_before_any_probe(hass, gateway):
    gateway.mac = "AA:BB:CC:DD:EE:99"
    call = await _setup(hass)
    results = await _test_address(hass, call, address=7)
    assert results["status"] == "failed"
    assert results["error_info"]["code"] == "IDENTITY_MISMATCH"
    assert gateway.probes == []


async def test_plain_esphome_node_without_scanner_component_is_rejected(hass, gateway):
    gateway.services = []
    gateway.entities = []
    call = await _setup(hass)
    results = await _test_address(hass, call, address=7)
    assert results["error_info"]["code"] == "BRIDGE_UNSUPPORTED"
    assert gateway.probes == []


async def test_changed_action_signature_is_rejected(hass, gateway):
    gateway.services[0].args.pop()
    call = await _setup(hass)
    results = await _test_address(hass, call, address=7)
    assert results["error_info"]["code"] == "BRIDGE_UNSUPPORTED"
    assert gateway.probes == []


async def test_incompatible_bridge_info_is_rejected(hass, gateway):
    gateway.info = lambda: {"v": 1, "bridge": 3, "buses": []}
    call = await _setup(hass)
    results = await _test_address(hass, call, address=7)
    assert results["error_info"]["code"] == "BRIDGE_UNSUPPORTED"
    assert gateway.probes == []


async def test_uncorrelated_results_are_ignored(hass, gateway):
    call = await _setup(hass)

    def stale_then_real(data):
        stale = {**gateway.firmware_result(data), "id": "someone-else", "values": [42, 42]}
        FakeClient.instances[-1].callback(TextSensorState(key=RESULT_KEY, state=json.dumps(stale)))
        return gateway.firmware_result(data)

    gateway.result_override = stale_then_real
    results = await _test_address(hass, call, address=7, register_count=2)
    assert results["responders"][0]["raw_values"] == [1234, 65535]


async def test_malformed_correlated_result_fails_the_scan(hass, gateway):
    call = await _setup(hass)
    gateway.result_override = lambda data: {
        "v": 1,
        "id": data["request_id"],
        "outcome": "responded",
    }
    results = await _test_address(hass, call, address=7)
    assert results["error_info"]["code"] == "RESPONSE_INVALID"


async def test_firmware_rejection_fails_the_scan_with_its_reason(hass, gateway):
    call = await _setup(hass)
    gateway.result_override = lambda data: {
        **gateway.firmware_result(data),
        "outcome": "gateway_error",
        "error": "busy",
    }
    results = await _test_address(hass, call, address=7)
    assert results["status"] == "failed"
    assert results["error_info"] == {
        "code": "FIRMWARE_REJECTED",
        "phase": "probe",
        "retryable": True,
    }
    assert "busy" in results["error"]


async def test_more_than_one_bus_requires_bus_selection(hass, gateway):
    gateway.buses = ["rs485_a", "rs485_b"]
    call = await _setup(hass)
    results = await _test_address(hass, call, address=7)
    assert results["error_info"]["code"] == "BUS_SELECTION_REQUIRED"
    assert gateway.probes == []


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"register_count": 5}, "Bridge v2 requires register_count<=4"),
        ({"timeout_ms": 99}, "Bridge v2 requires timeout_ms 100–2000"),
        ({"probe_type": "device_identification"}, "Bridge v2 requires probe_type"),
        ({"pause_normal_polling": True}, "Bridge v2 cannot pause Normal Polling yet"),
    ],
)
async def test_service_layer_enforces_v2_limits_without_bus_traffic(
    hass, gateway, changes, message
):
    call = await _setup(hass)
    with pytest.raises(ServiceValidationError, match=message):
        await call(
            "test_address",
            {"provider": "esphome", "gateway_id": GATEWAY_ID, "address": 1, **changes},
        )
    assert FakeClient.instances == []


async def test_check_gateway_verifies_v2_without_sending_a_probe(hass, gateway):
    call = await _setup(hass)
    checked = await call("check_gateway", {"gateway_id": GATEWAY_ID})
    assert checked["health"]["bridge_status"] == "v2_signature_verified"
    assert checked["health"]["buses"] == ["rs485"]
    assert gateway.probes == []


async def test_check_gateway_reports_a_missing_scanner_component(hass, gateway):
    gateway.services = []
    call = await _setup(hass)
    with pytest.raises(HomeAssistantError, match="modbus_scanner component"):
        await call("check_gateway", {"gateway_id": GATEWAY_ID})
