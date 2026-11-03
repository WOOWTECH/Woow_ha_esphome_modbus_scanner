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
INFO_KEY, RESULT_KEY, LEASE_KEY = 1, 2, 3
PROBE_KEY, RELEASE_KEY = 10, 11
LEASE = CONTRACT["lease"]


def _args(action):
    return [
        UserServiceArg(arg["name"], ARG_TYPES[arg["type"]])
        for arg in CONTRACT["actions"][action]["args"]
    ]


class FakeV2Gateway:
    """A node running the modbus_scanner component, speaking bridge v2 per the contract.

    ``devices`` maps (bus, slave) to a responder: a list of register values, or an int
    Modbus exception code. Anything else times out, like a silent RS-485 address.
    ``pollers`` maps a bus to its Pausable Poller table as (name, address) pairs, and
    ``serial`` a bus to the serial parameters its info entry reports. Each Bus holds its own
    Scan Lease, following the contract's lease rules except the timers (firmware host tests
    own those). Every sensor state goes to every connected API client, as on a real node.
    """

    def __init__(self, *, mac=MAC, buses=("rs485",), devices=None, pollers=None, serial=None):
        self.mac = mac
        self.buses = list(buses)
        self.devices = devices or {}
        self.pollers = pollers or {}
        self.serial = serial or {}
        self.probes = []
        self.releases = []
        self.paused = set()  # (bus, index) currently held paused by a lease
        self.leases = {}  # bus -> {"bus", "scan", "pollers", "active", "reason"}
        self.result_override = None
        self.clients = []  # connected FakeClients subscribed to states
        self.services = [
            UserService(
                name=CONTRACT["actions"]["probe"]["name"], key=PROBE_KEY, args=_args("probe")
            ),
            UserService(
                name=CONTRACT["actions"]["release"]["name"],
                key=RELEASE_KEY,
                args=_args("release"),
            ),
        ]
        self.entities = [
            TextSensorInfo(key=INFO_KEY, name=CONTRACT["text_sensors"]["info"]["name"]),
            TextSensorInfo(key=RESULT_KEY, name=CONTRACT["text_sensors"]["result"]["name"]),
            TextSensorInfo(key=LEASE_KEY, name=CONTRACT["text_sensors"]["lease"]["name"]),
        ]

    def publish(self, key, payload):
        """Publish a sensor state to every connected client."""
        for client in list(self.clients):
            if client.connected:
                client.publish(key, payload)

    @property
    def lease(self):
        """The most recent Scan Lease of any Bus (single-Bus tests)."""
        return next(reversed(self.leases.values()), None)

    def info(self):
        def entry(bus):
            row = {
                "bus": bus,
                "pollers": [
                    {"index": index, "name": name, "address": address}
                    for index, (name, address) in enumerate(self.pollers.get(bus, ()))
                ],
            }
            if bus in self.serial:
                row["serial"] = dict(self.serial[bus])
            return row

        return {
            "v": CONTRACT["info"]["schema_version"],
            "bridge": CONTRACT["bridge_version"],
            "buses": [entry(bus) for bus in self.buses],
        }

    @staticmethod
    def lease_message(bus, scan, state, pollers=(), reason=None):
        message = {
            "v": LEASE["schema_version"],
            "bus": bus,
            "scan": scan,
            "state": state,
            "pollers": list(pollers),
        }
        if reason is not None:
            message["reason"] = reason
        return message

    def end_lease(self, reason, bus=None):
        """The Gateway ends a Bus's lease (released, idle, hard_limit or superseded)."""
        lease = self.leases[bus] if bus is not None else self.lease
        lease.update(active=False, reason=reason)
        self.paused = {item for item in self.paused if item[0] != lease["bus"]}
        self.publish(
            LEASE_KEY,
            self.lease_message(lease["bus"], lease["scan"], "ended", lease["pollers"], reason),
        )

    def _lease_for(self, data):
        bus = data["bus"]
        lease = self.leases.get(bus)
        if lease and lease["active"] and lease["scan"] != data["scan_id"]:
            self.end_lease("superseded", bus)
        if lease and (lease["active"] or lease["scan"] == data["scan_id"]):
            return
        selected = (
            [int(i) for i in data["pause_pollers"].split(",")] if data["pause_pollers"] else []
        )
        if not selected:
            return
        self.leases[bus] = {"bus": bus, "scan": data["scan_id"], "pollers": selected}
        self.leases[bus]["active"] = True
        self.paused |= {(bus, index) for index in selected}
        self.publish(LEASE_KEY, self.lease_message(bus, data["scan_id"], "active", selected))

    def release(self, data):
        self.releases.append(dict(data))
        if data["bus"] not in self.buses:
            return
        lease = self.leases.get(data["bus"])
        if lease and lease["scan"] == data["scan_id"]:
            if lease["active"]:
                self.end_lease("released", data["bus"])
            else:
                self.publish(
                    LEASE_KEY,
                    self.lease_message(
                        lease["bus"], lease["scan"], "ended", lease["pollers"], lease["reason"]
                    ),
                )
            return
        self.publish(LEASE_KEY, self.lease_message(data["bus"], data["scan_id"], "none"))

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
        table = self.pollers.get(data["bus"], ())
        if data["pause_pollers"] and not all(
            part.isdigit() and int(part) < len(table) for part in data["pause_pollers"].split(",")
        ):
            return "invalid_poller"
        return None

    def execute(self, data):
        """Firmware behaviour: one result per probe, published on the result sensor."""
        self.probes.append(dict(data))
        if self._rejection(data) is None:
            self._lease_for(data)
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
        self.on_stop = kwargs.get("on_stop")

    async def device_info(self):
        return SimpleNamespace(mac_address=self.gateway.mac)

    async def list_entities_services(self):
        return list(self.gateway.entities), list(self.gateway.services)

    def subscribe_states(self, callback):
        self.callback = callback
        self.gateway.clients.append(self)
        callback(TextSensorState(key=INFO_KEY, state=json.dumps(self.gateway.info())))

    # Seconds, or None to deliver each state at once. When set, states are sent like the
    # ESPHome API server does: batched per connection, and only the latest state of each
    # entity in a batch is sent (api_connection.h DeferredBatch::add_item deduplicates).
    batch_delay = None

    def publish(self, key, payload):
        state = json.dumps(payload, separators=(",", ":"))
        if self.batch_delay is None:
            self.callback(TextSensorState(key=key, state=state))
            return
        batch = self.__dict__.setdefault("batch", {})
        if not batch:
            asyncio.get_running_loop().call_later(self.batch_delay, self._flush)
        batch[key] = state

    def _flush(self):
        batch, self.batch = self.batch, {}
        for key, state in batch.items():
            if self.connected:
                self.callback(TextSensorState(key=key, state=state))

    def execute_service(self, service, data):
        if not self.connected:
            raise ConnectionError("not connected")
        if service.key == RELEASE_KEY:
            self.gateway.release(data)
            return None
        result = self.gateway.execute(data)
        if result is not None:
            self.gateway.publish(RESULT_KEY, result)
        return None

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
        "pause_normal_polling_supported": True,
    }


async def test_timeouts_are_counted_but_exceptions_are_listed(hass, gateway):
    call = await _setup(hass)
    timed_out = await _test_address(hass, call, address=200)
    assert timed_out["outcome_counts"]["timeout"] == 1
    assert timed_out["responders"] == []

    excepted = await _test_address(hass, call, address=9)
    [row] = excepted["responders"]
    assert (row["outcome"], row["exception_code"]) == ("modbus_exception", 2)


async def test_default_probe_is_fc03_single_register_on_a_bus_without_pollers(hass, gateway):
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


@pytest.mark.parametrize(
    ("address", "changes"),
    [
        (7, {"v": 2}),
        (7, {"slave": 8}),
        (7, {"fc": 3.0}),
        (7, {"latency_ms": -1}),
        (7, {"values": [1, 2, 3]}),
        (7, {"values": [1, 70000]}),
        (9, {"exception": 0}),
        (9, {"exception": None}),
        (200, {"outcome": "gateway_error", "error": "made_up"}),
        (200, {"outcome": "modbus_exception"}),
    ],
)
async def test_correlated_result_breaking_the_contract_fails_the_scan(
    hass, gateway, address, changes
):
    call = await _setup(hass)
    gateway.result_override = lambda data: {**gateway.firmware_result(data), **changes}
    results = await _test_address(hass, call, address=address, register_count=2)
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


# ---- Scan Lease: a Scan pauses every Pausable Poller on its Bus ----

POLLERS = [("meter", 1), ("inverter", 2)]
POLLER_TABLE = [
    {"index": 0, "name": "meter", "address": 1},
    {"index": 1, "name": "inverter", "address": 2},
]


@pytest.fixture
def polled(gateway):
    gateway.pollers = {"rs485": list(POLLERS)}
    return gateway


async def _scan(hass, call, start=8, end=10, **fields):
    started = await call(
        "start_scan",
        {
            "provider": "esphome",
            "gateway_id": GATEWAY_ID,
            "start_id": start,
            "end_id": end,
            "inter_request_delay_ms": 0,
            "safety_confirmed": True,
            **fields,
        },
    )
    return started["scan_id"]


async def _finished(hass, call, scan_id):
    await _settle(hass)
    return await call("get_scan_status", {"scan_id": scan_id})


async def test_scan_pauses_every_pausable_poller_and_releases_when_done(hass, polled):
    call = await _setup(hass)
    status = await _finished(hass, call, await _scan(hass, call))

    assert status["status"] == "completed"
    assert [probe["pause_pollers"] for probe in polled.probes] == ["0,1"] * 3
    [scan_id] = {probe["scan_id"] for probe in polled.probes}
    assert polled.releases == [{"bus": "rs485", "scan_id": scan_id}]
    assert polled.paused == set()
    assert status["lease_status"] == "ended"
    assert status["lease_end_reason"] == "released"
    assert status["paused_pollers"] == POLLER_TABLE
    results = await call("get_scan_results", {"scan_id": status["scan_id"]})
    assert (results["lease_status"], results["lease_end_reason"]) == ("ended", "released")


async def test_cancelled_scan_releases_the_lease_immediately(hass, polled):
    call = await _setup(hass)
    held = []
    polled.result_override = held.append  # the first probe stays on the wire
    scan = await _scan(hass, call, start=1, end=20)
    for _ in range(500):
        if held:
            break
        await asyncio.sleep(0.01)
    running = await call("get_scan_status", {"scan_id": scan})
    assert running["lease_status"] == "active"
    assert polled.paused == {("rs485", 0), ("rs485", 1)}

    await call("cancel_scan", {"scan_id": scan})
    FakeClient.instances[-1].publish(RESULT_KEY, polled.firmware_result(held[0]))
    status = await _finished(hass, call, scan)

    assert status["status"] == "cancelled"
    assert len(polled.probes) == 1  # the probe on the wire finishes; no further probe is sent
    assert polled.releases == [{"bus": "rs485", "scan_id": held[0]["scan_id"]}]
    assert polled.paused == set()
    assert (status["lease_status"], status["lease_end_reason"]) == ("ended", "released")


async def test_lease_ended_by_the_gateway_is_reported_with_its_reason(hass, polled):
    call = await _setup(hass)

    def hard_limit_at_9(data):
        if data["slave"] == 9:
            polled.end_lease("hard_limit")
        return polled.firmware_result(data)

    polled.result_override = hard_limit_at_9
    status = await _finished(hass, call, await _scan(hass, call))

    assert status["status"] == "completed"  # the Scan goes on without pausing
    assert len(polled.probes) == 3
    assert (status["lease_status"], status["lease_end_reason"]) == ("ended", "hard_limit")


async def test_disconnect_mid_scan_leaves_recovery_to_the_gateway(hass, polled):
    call = await _setup(hass)

    def drop_connection(data):
        client = FakeClient.instances[-1]
        client.connected = False
        asyncio.get_running_loop().create_task(client.on_stop(False))

    polled.result_override = drop_connection
    status = await _finished(hass, call, await _scan(hass, call))

    assert status["status"] == "failed"
    assert status["error_info"]["code"] == "API_DISCONNECTED"
    assert polled.releases == []
    # HA cannot confirm the ending; the Gateway resumes polling by itself after the idle time.
    assert status["lease_status"] == "unconfirmed"
    assert status["lease_end_reason"] is None


async def test_unanswered_release_is_reported_as_unconfirmed(hass, polled, monkeypatch):
    monkeypatch.setattr(v2_provider, "_RELEASE_ANSWER_S", 0.05)
    polled.release = polled.releases.append  # the Gateway never answers
    call = await _setup(hass)
    status = await _finished(hass, call, await _scan(hass, call, end=8))
    assert len(polled.releases) == 1
    assert status["status"] == "completed"
    assert status["lease_status"] == "unconfirmed"


async def test_scan_without_pausing_sends_no_selection_and_no_release(hass, polled):
    call = await _setup(hass)
    status = await _finished(hass, call, await _scan(hass, call, pause_normal_polling=False))
    assert [probe["pause_pollers"] for probe in polled.probes] == [""] * 3
    assert polled.releases == []
    assert (status["lease_status"], status["paused_pollers"]) == ("none", [])


async def test_bus_without_pollers_needs_no_lease(hass, gateway):
    call = await _setup(hass)
    status = await _finished(hass, call, await _scan(hass, call))
    assert [probe["pause_pollers"] for probe in gateway.probes] == [""] * 3
    assert gateway.releases == []
    assert status["lease_status"] == "none"


@pytest.mark.parametrize("missing", ["release_action", "lease_sensor"])
async def test_gateway_without_lease_support_is_rejected(hass, polled, missing):
    if missing == "release_action":
        polled.services = [s for s in polled.services if s.key != RELEASE_KEY]
    else:
        polled.entities = [e for e in polled.entities if e.key != LEASE_KEY]
    call = await _setup(hass)
    results = await _test_address(hass, call, address=7)
    assert results["error_info"]["code"] == "BRIDGE_UNSUPPORTED"
    assert polled.probes == []


async def test_malformed_poller_table_is_rejected(hass, polled):
    polled.info = lambda: {
        "v": 1,
        "bridge": 2,
        "buses": [{"bus": "rs485", "pollers": [{"index": "0", "name": "meter"}]}],
    }
    call = await _setup(hass)
    results = await _test_address(hass, call, address=7)
    assert results["error_info"]["code"] == "BRIDGE_UNSUPPORTED"
    assert polled.probes == []


async def test_foreign_and_malformed_lease_messages_are_ignored(hass, polled):
    call = await _setup(hass)

    def noise(data):
        client = FakeClient.instances[-1]
        client.publish(
            LEASE_KEY, polled.lease_message("rs485", "someone-else", "ended", [0], "idle")
        )
        client.callback(TextSensorState(key=LEASE_KEY, state="{not json"))
        client.publish(LEASE_KEY, {"v": 1, "bus": "rs485", "scan": data["scan_id"], "state": "odd"})
        client.publish(
            LEASE_KEY, polled.lease_message("rs485", data["scan_id"], "ended", [0], "made_up")
        )
        return polled.firmware_result(data)

    polled.result_override = noise
    status = await _finished(hass, call, await _scan(hass, call, end=8))
    assert (status["lease_status"], status["lease_end_reason"]) == ("ended", "released")


async def test_check_gateway_lists_the_pausable_pollers(hass, polled):
    call = await _setup(hass)
    checked = await call("check_gateway", {"gateway_id": GATEWAY_ID})
    assert checked["health"]["pausable_pollers"] == {"rs485": POLLER_TABLE}
    assert polled.probes == []
