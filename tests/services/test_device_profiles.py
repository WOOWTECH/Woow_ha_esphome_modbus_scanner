"""Device Profile import and management through the HA service seam."""

import asyncio
from copy import deepcopy
import json

from homeassistant.core import Context
from homeassistant.exceptions import ServiceValidationError, Unauthorized
import pytest
from test_bridge_v2 import GATEWAY_ID, FakeClient, FakeV2Gateway
from test_bridge_v2 import _setup as setup_v2

from custom_components.woow_esphome_modbus_scanner.const import DATA_COORDINATOR, DOMAIN
from custom_components.woow_esphome_modbus_scanner.modbus_scan.bridge_v2 import (
    provider as v2_provider,
)
from custom_components.woow_esphome_modbus_scanner.services import async_register_services

STORAGE_KEY = f"{DOMAIN}.device_profiles"

METER = {
    "schema_version": 1,
    "id": "acme-meter",
    "name": "Acme Meter",
    "vendor": "Acme",
    "model": "M-100",
    "version": "1.2.0",
    "function_codes": [4],
    "defaults": {
        "slave_start": 2,
        "slave_end": 5,
        "register": 16,
        "count": 2,
        "timeout_ms": 300,
        "inter_request_delay_ms": 0,
        "retries": 0,
    },
    "allowed_registers": [16, 17, 18, 19, 32],
    "fields": [
        {"register": 16, "name": "Voltage", "unit": "V", "scale": 0.1, "data_type": "u16"},
        {"register": 18, "name": "Current", "unit": "A", "scale": 0.01, "data_type": "s16"},
    ],
}


async def _setup(hass, *, active=True):
    await hass.auth.async_create_user("owner")  # the first user is the owner
    user = await hass.auth.async_create_user("profile operator")
    if not active:
        await hass.auth.async_update_user(user, is_active=False)
    async_register_services(hass)
    context = Context(user_id=user.id)

    async def call(service, data=None):
        return await hass.services.async_call(
            DOMAIN, service, data or {}, blocking=True, return_response=True, context=context
        )

    return call


async def _settle(hass):
    await asyncio.gather(*hass.data[DOMAIN][DATA_COORDINATOR]._tasks.values())


async def _ids(call):
    return [item["id"] for item in (await call("list_device_profiles"))["profiles"]]


async def test_generic_device_profile_is_listed_as_built_in(hass):
    call = await _setup(hass)
    response = await call("list_device_profiles")
    [generic] = response["profiles"]
    assert (generic["id"], generic["builtin"], generic["deletable"]) == ("generic", True, False)
    assert generic["function_codes"] == [3, 4]
    assert generic["allowed_registers"] is None
    assert generic["limits"]["register_count_max"] == 4
    assert (generic["limits"]["timeout_ms_min"], generic["limits"]["timeout_ms_max"]) == (100, 2000)
    assert (generic["limits"]["slave_min"], generic["limits"]["slave_max"]) == (1, 247)


async def test_imported_profile_is_listed_and_exports_the_same_document(hass):
    call = await _setup(hass)
    imported = await call("import_device_profile", {"profile": METER})
    assert (imported["profile"]["id"], imported["replaced"]) == ("acme-meter", False)

    [generic, meter] = (await call("list_device_profiles"))["profiles"]
    assert generic["id"] == "generic"
    assert (meter["name"], meter["vendor"], meter["model"], meter["version"]) == (
        "Acme Meter",
        "Acme",
        "M-100",
        "1.2.0",
    )
    assert (meter["builtin"], meter["deletable"]) == (False, True)
    assert meter["allowed_registers"] == [16, 17, 18, 19, 32]
    assert meter["limits"]["probe_types"] == ["input_register"]
    assert meter["fields"][1]["data_type"] == "s16"

    exported = await call("export_device_profile", {"profile_id": "acme-meter"})
    assert exported["profile"] == METER


async def test_profile_can_be_uploaded_as_json_text(hass):
    call = await _setup(hass)
    await call("import_device_profile", {"profile": json.dumps(METER)})
    assert await _ids(call) == ["generic", "acme-meter"]


async def test_importing_an_existing_id_replaces_it(hass):
    call = await _setup(hass)
    await call("import_device_profile", {"profile": METER})
    newer = {**METER, "version": "2.0.0"}
    response = await call("import_device_profile", {"profile": newer})
    assert response["replaced"] is True
    exported = await call("export_device_profile", {"profile_id": "acme-meter"})
    assert exported["profile"]["version"] == "2.0.0"
    assert await _ids(call) == ["generic", "acme-meter"]


def _broken(**changes):
    document = deepcopy(METER)
    for path, value in changes.items():
        target = document
        *parents, leaf = path.split("__")
        for parent in parents:
            target = target[int(parent)] if isinstance(target, list) else target[parent]
        if value is ...:
            del target[leaf]
        else:
            target[leaf] = value
    return document


@pytest.mark.parametrize(
    ("document", "path", "message"),
    [
        ("{not json", "$", "not valid JSON (line 1, column 2)"),
        ([1, 2], "$", "must be a JSON object"),
        (_broken(schema_version=2), "schema_version", "must be 1"),
        (_broken(id=...), "id", "lowercase letters"),
        (_broken(id="Acme Meter"), "id", "lowercase letters"),
        (_broken(id="generic"), "id", "reserved"),
        (_broken(name=""), "name", "non-empty string"),
        (_broken(vendor=...), "vendor", "is required"),
        (_broken(function_codes=[]), "function_codes", "non-empty list"),
        (_broken(function_codes=[6]), "function_codes[0]", "FC06 is a write function code"),
        (_broken(function_codes=[3, 1]), "function_codes[1]", "must be 3"),
        (_broken(function_codes=[3, 3]), "function_codes", "must not repeat"),
        (_broken(defaults__count=5), "defaults.count", "integer from 1 to 4"),
        (_broken(defaults__count=True), "defaults.count", "integer from 1 to 4"),
        (_broken(defaults__timeout_ms=99), "defaults.timeout_ms", "integer from 100 to 2000"),
        (_broken(defaults__retries=6), "defaults.retries", "integer from 0 to 5"),
        # Above the widest delay any Gateway accepts (a Legacy Gateway's 5000 ms).
        (_broken(defaults__inter_request_delay_ms=5001), "defaults.inter_request_delay_ms",
         "integer from 0 to 5000"),
        (_broken(defaults__slave_end=248), "defaults.slave_end", "integer from 1 to 247"),
        (_broken(defaults__slave_start=9), "defaults.slave_end", "at least slave_start"),
        (_broken(defaults__slave_end=...), "defaults", "given together"),
        (_broken(defaults__function_code=3), "defaults.function_code", "function_codes"),
        (_broken(defaults__register=20), "defaults.register", "allowed_registers"),
        # 32 is allowed but 33 is not: the whole default block must be allowed.
        (_broken(defaults__register=32), "defaults.count", "every register of the default block"),
        (_broken(defaults__speed=1), "defaults.speed", "not a Device Profile field"),
        (_broken(allowed_registers=[]), "allowed_registers", "non-empty list"),
        (_broken(allowed_registers=[16, 70000]), "allowed_registers[1]", "0 to 65535"),
        (_broken(fields__0__data_type="f32"), "fields[0].data_type", "'u16' or 's16'"),
        (_broken(fields__0__register=20), "fields[0].register", "allowed_registers"),
        (_broken(fields__1__register=16), "fields[1].register", "already defined"),
        (_broken(fields__0__scale=0), "fields[0].scale", "non-zero"),
        (_broken(fields__0__name=...), "fields[0].name", "is required"),
        (_broken(colour="red"), "colour", "not a Device Profile field"),
        ("x" * (64 * 1024 + 1), "$", "at most 65536 bytes"),
        (_broken(model="m" * 65), "model", "at most 64 characters"),
        (_broken(defaults=[]), "defaults", "must be an object"),
        (_broken(defaults__count=4, defaults__register=65534, allowed_registers=...),
         "defaults.count", "end at or before 65535"),
        (_broken(allowed_registers=[16, 16]), "allowed_registers", "must not repeat"),
        (_broken(allowed_registers=list(range(1025))), "allowed_registers", "at most 1024"),
        (_broken(fields={}), "fields", "must be a list"),
        (_broken(fields=[{"register": 16, "name": "x"}] * 257), "fields", "at most 256"),
        (_broken(fields=[1]), "fields[0]", "must be an object"),
        (_broken(fields__0__register=...), "fields[0].register", "is required"),
        (_broken(fields__0__unit="u" * 17), "fields[0].unit", "at most 16 characters"),
        (_broken(fields__0__scale="10"), "fields[0].scale", "finite, non-zero number"),
        (_broken(fields__0__scale=float("inf")), "fields[0].scale", "finite, non-zero number"),
    ],
)
async def test_invalid_profile_is_rejected_with_a_field_level_error(
    hass, document, path, message
):
    call = await _setup(hass)
    with pytest.raises(ServiceValidationError) as err:
        await call("import_device_profile", {"profile": document})
    assert f"{path}: " in str(err.value)
    assert message in str(err.value).split(f"{path}: ", 1)[1]
    assert await _ids(call) == ["generic"]


async def test_every_field_error_is_reported_at_once(hass):
    call = await _setup(hass)
    with pytest.raises(ServiceValidationError) as err:
        await call(
            "import_device_profile",
            {"profile": _broken(name="", defaults__count=9, function_codes=[16])},
        )
    message = str(err.value)
    assert all(path in message for path in ("name:", "defaults.count:", "function_codes[0]:"))


async def test_imported_profiles_are_kept_in_ha_storage(hass, hass_storage):
    call = await _setup(hass)
    await call("import_device_profile", {"profile": METER})
    assert hass_storage[STORAGE_KEY]["data"]["profiles"] == [METER]


async def test_profiles_restored_from_storage_are_available(hass, hass_storage):
    broken = {**METER, "id": "broken", "function_codes": [16]}
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "key": STORAGE_KEY,
        "data": {"profiles": [METER, broken]},
    }
    call = await _setup(hass)
    # A stored document that no longer validates is skipped instead of breaking the scanner.
    assert await _ids(call) == ["generic", "acme-meter"]


async def test_generic_profile_cannot_be_deleted(hass):
    call = await _setup(hass)
    with pytest.raises(ServiceValidationError, match="Generic Device Profile cannot be deleted"):
        await call("delete_device_profile", {"profile_id": "generic"})
    assert await _ids(call) == ["generic"]


async def test_deleting_an_unknown_profile_is_a_validation_error(hass):
    call = await _setup(hass)
    with pytest.raises(ServiceValidationError, match="Unknown Device Profile: nope"):
        await call("delete_device_profile", {"profile_id": "nope"})
    with pytest.raises(ServiceValidationError, match="Unknown Device Profile: nope"):
        await call("export_device_profile", {"profile_id": "nope"})


async def test_deleted_profile_is_gone_and_can_no_longer_be_selected(hass, hass_storage):
    call = await _setup(hass)
    await call("import_device_profile", {"profile": METER})
    assert await call("delete_device_profile", {"profile_id": "acme-meter"}) == {
        "deleted": "acme-meter"
    }
    assert await _ids(call) == ["generic"]
    assert hass_storage[STORAGE_KEY]["data"]["profiles"] == []
    with pytest.raises(ServiceValidationError, match="Unknown Device Profile: acme-meter"):
        await call("test_address", {"address": 1, "device_profile_id": "acme-meter"})


async def test_profile_used_by_a_running_scan_cannot_be_deleted(hass):
    call = await _setup(hass)
    await call("import_device_profile", {"profile": METER})
    started = await call(
        "start_scan",
        {
            "device_profile_id": "acme-meter",
            "inter_request_delay_ms": 200,
            "safety_confirmed": True,
        },
    )
    with pytest.raises(ServiceValidationError, match=f"running Scan {started['scan_id']}"):
        await call("delete_device_profile", {"profile_id": "acme-meter"})
    await call("cancel_scan", {"scan_id": started["scan_id"]})
    await _settle(hass)
    await call("delete_device_profile", {"profile_id": "acme-meter"})
    # The finished Scan keeps the label it ran with.
    results = await call("get_scan_results", {"scan_id": started["scan_id"]})
    assert results["device_profile"] == {
        "id": "acme-meter",
        "name": "Acme Meter",
        "version": "1.2.0",
    }


async def test_inactive_users_cannot_change_profiles(hass):
    call = await _setup(hass, active=False)
    with pytest.raises(Unauthorized):
        await call("import_device_profile", {"profile": METER})
    with pytest.raises(Unauthorized):
        await call("delete_device_profile", {"profile_id": "acme-meter"})


async def test_scan_without_a_profile_is_labelled_generic(hass):
    call = await _setup(hass)
    started = await call(
        "start_scan",
        {"start_id": 1, "end_id": 3, "inter_request_delay_ms": 0, "safety_confirmed": True},
    )
    assert started["device_profile"] == {
        "id": "generic",
        "name": "Generic Device Profile",
        "version": "1",
    }
    await _settle(hass)
    results = await call("get_scan_results", {"scan_id": started["scan_id"]})
    assert results["device_profile"]["id"] == "generic"
    history = await call("get_history")
    assert history["scans"][0]["device_profile"]["id"] == "generic"


async def test_profile_defaults_fill_every_omitted_field(hass):
    call = await _setup(hass)
    await call("import_device_profile", {"profile": METER})
    started = await call(
        "start_scan", {"device_profile_id": "acme-meter", "safety_confirmed": True}
    )
    await _settle(hass)
    results = await call("get_scan_results", {"scan_id": started["scan_id"]})
    assert results["device_profile"]["id"] == "acme-meter"
    assert results["total_addresses"] == 4  # slave_start 2 .. slave_end 5
    # Mock found_default in 2..5: ID 3 replies with registers, ID 5 with an exception.
    row, exception = results["responders"]
    assert (exception["address"], exception["outcome"]) == (5, "modbus_exception")
    assert (row["address"], row["register_address"], row["raw_values"]) == (
        3,
        16,
        [0x0310, 0x0311],
    )
    assert "FC04" in row["detail"]


async def test_explicit_fields_override_profile_defaults(hass):
    call = await _setup(hass)
    await call("import_device_profile", {"profile": METER})
    started = await call(
        "test_address",
        {"device_profile_id": "acme-meter", "address": 3, "register_address": 18},
    )
    await _settle(hass)
    [row] = (await call("get_scan_results", {"scan_id": started["scan_id"]}))["responders"]
    assert (row["register_address"], len(row["raw_values"])) == (18, 2)


async def test_scan_without_range_and_without_profile_range_is_rejected(hass):
    call = await _setup(hass)
    with pytest.raises(ServiceValidationError, match="start_id and end_id are required"):
        await call("start_scan", {"safety_confirmed": True})


async def test_large_default_range_from_a_profile_still_needs_confirmation(hass):
    call = await _setup(hass)
    wide = {**METER, "id": "wide", "defaults": {"slave_start": 1, "slave_end": 247}}
    await call("import_device_profile", {"profile": wide})
    with pytest.raises(ServiceValidationError, match="large_range_confirmed"):
        await call("start_scan", {"device_profile_id": "wide", "safety_confirmed": True})


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"register_address": 20}, "read allowlist"),
        # The first register is allowed, the next one is not: the whole block is checked.
        ({"register_address": 32, "register_count": 2}, r"Register 33 \(0x0021\) is not in"),
        ({"register_address": 16, "register_count": 4}, None),
        ({"probe_type": "holding_register"}, "requires probe_type in: input_register"),
        ({"probe_type": "device_identification"}, "requires probe_type"),
    ],
)
async def test_service_layer_enforces_the_selected_profile(hass, changes, message):
    call = await _setup(hass)
    await call("import_device_profile", {"profile": METER})
    if message is None:  # a block made only of allowed registers is accepted
        await call("test_address", {"device_profile_id": "acme-meter", "address": 3, **changes})
        return
    with pytest.raises(ServiceValidationError, match=message):
        await call("test_address", {"device_profile_id": "acme-meter", "address": 3, **changes})
    with pytest.raises(ServiceValidationError, match=message):
        await call(
            "start_scan",
            {"device_profile_id": "acme-meter", "safety_confirmed": True, **changes},
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"register_count": 5}, "register_count<=4"),
        ({"timeout_ms": 99}, "timeout_ms 100"),
        ({"timeout_ms": 2001}, "timeout_ms 100"),
    ],
)
async def test_generic_profile_bounds_apply_to_the_mock_gateway_too(hass, changes, message):
    call = await _setup(hass)
    with pytest.raises(ServiceValidationError, match=message):
        await call("test_address", {"address": 1, **changes})


@pytest.fixture
def v2_gateway(monkeypatch):
    node = FakeV2Gateway(devices={("rs485", 3): [7, 8]})
    FakeClient.gateway = node
    FakeClient.instances = []
    monkeypatch.setattr(v2_provider, "APIClient", FakeClient)
    return node


async def test_v2_scan_uses_the_profile_inside_the_gateway_limits(hass, v2_gateway):
    call = await setup_v2(hass)
    await call("import_device_profile", {"profile": METER})
    target = {"provider": "esphome", "gateway_id": GATEWAY_ID, "device_profile_id": "acme-meter"}

    with pytest.raises(ServiceValidationError, match="read allowlist"):
        await call("test_address", {**target, "address": 3, "register_address": 20})
    # Gateway limits still apply on top of the profile: Generic allows the mock-only
    # identification probe, Bridge v2 does not.
    with pytest.raises(ServiceValidationError, match="Bridge v2 requires probe_type"):
        await call(
            "test_address",
            {
                **target,
                "device_profile_id": "generic",
                "address": 3,
                "probe_type": "device_identification",
            },
        )
    assert FakeClient.instances == []

    started = await call("test_address", {**target, "address": 3})
    await _settle(hass)
    [probe] = v2_gateway.probes
    assert (probe["function_code"], probe["register"], probe["count"], probe["timeout_ms"]) == (
        4,
        16,
        2,
        300,
    )
    results = await call("get_scan_results", {"scan_id": started["scan_id"]})
    assert results["device_profile"]["id"] == "acme-meter"
    assert results["responders"][0]["raw_values"] == [7, 8]
