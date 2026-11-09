"""Request handling of the #16 bench simulator. No serial port is opened."""

from pathlib import Path

import pytest

from tools.rtu_bench_simulator import (
    FrameBuffer,
    build_slaves,
    crc16,
    handle,
    load_config,
    with_crc,
)

BENCH = Path(__file__).parents[2] / "tools" / "bench_profiles" / "bench.json"


def read(slave, function, address, count=1):
    body = bytes([slave, function]) + address.to_bytes(2, "big") + count.to_bytes(2, "big")
    return with_crc(body)


@pytest.fixture
def slaves():
    return build_slaves({"1": {"holding": {"0x0000": "counter", "5": 7}, "input": {"0": 9}}})


def test_crc_matches_known_frame():
    # 01 03 00 00 00 01 -> CRC 84 0A (standard Modbus example)
    assert crc16(bytes.fromhex("010300000001")) == bytes.fromhex("840a")


def test_configured_slave_replies_with_value(slaves):
    reply, entry = handle(slaves, read(1, 4, 0))
    assert reply == with_crc(bytes.fromhex("01 04 02 00 09"))
    assert entry == {"slave": 1, "fc": 4, "addr": 0, "count": 1, "result": "reply", "values": [9]}


def test_unconfigured_slave_is_silent(slaves):
    reply, entry = handle(slaves, read(2, 3, 0))
    assert reply is None
    assert entry["result"] == "silent"


def test_broadcast_is_silent(slaves):
    reply, entry = handle(slaves, read(0, 3, 0))
    assert reply is None
    assert entry["result"] == "broadcast"


def test_counter_rises_on_every_read(slaves):
    values = [handle(slaves, read(1, 3, 0))[1]["values"][0] for _ in range(3)]
    assert values == [0, 1, 2]


def test_missing_register_is_illegal_address(slaves):
    reply, entry = handle(slaves, read(1, 3, 1))
    assert reply == with_crc(bytes([1, 0x83, 2]))
    assert entry["result"] == "exception"


def test_read_spanning_a_gap_is_illegal_address(slaves):
    assert handle(slaves, read(1, 3, 4, 2))[1]["code"] == 2


def test_bad_count_is_illegal_value(slaves):
    assert handle(slaves, read(1, 3, 0, 0))[1]["code"] == 3


def test_unsupported_function_is_illegal_function(slaves):
    frame = with_crc(bytes.fromhex("01 01 00 00 00 01"))
    reply, entry = handle(slaves, frame)
    assert reply == with_crc(bytes([1, 0x81, 1]))


def test_write_single_register_echoes_and_stores(slaves):
    frame = with_crc(bytes.fromhex("010600050010"))
    reply, entry = handle(slaves, frame)
    assert reply == frame
    assert entry["result"] == "written"
    assert handle(slaves, read(1, 3, 5))[1]["values"] == [16]


def test_bad_crc_is_ignored(slaves):
    frame = read(1, 3, 0)[:-1] + b"\x00"
    reply, entry = handle(slaves, frame)
    assert reply is None
    assert entry["result"] == "unparsed"


def test_frame_buffer_splits_back_to_back_requests():
    frames = FrameBuffer()
    a, b = read(1, 3, 0), read(10, 4, 0)
    data = a + b
    assert frames.feed(data[:5]) == []
    assert frames.feed(data[5:]) == [a, b]


def test_frame_buffer_resyncs_after_noise():
    frames = FrameBuffer()
    a = read(1, 3, 0)
    assert frames.feed(b"\xff" + a) == [a]
    assert frames.resyncs >= 1


def test_frame_buffer_gap_discards_partial():
    frames = FrameBuffer()
    frames.feed(read(1, 3, 0)[:3])
    assert len(frames.gap()) == 3
    assert frames.feed(read(1, 3, 0)) == [read(1, 3, 0)]


@pytest.mark.parametrize(
    "raw",
    [
        {"0": {}},
        {"248": {}},
        {"1": {"coils": {}}},
        {"1": {"holding": {"0": 70000}}},
        {"1": {"holding": {"0": True}}},
    ],
)
def test_invalid_slave_config_is_rejected(raw):
    with pytest.raises(ValueError):
        build_slaves(raw)


def test_bench_profile_loads_and_lines_do_not_share_responders():
    lines = {line.name: line for line in load_config(BENCH)}
    assert set(lines) == {"X", "Y"}
    x, y = set(lines["X"].slaves), set(lines["Y"].slaves)
    assert x & y == {1}  # slave 1 is each Gateway's Pausable Poller target
    for name, prefix in (("X", 0xA000), ("Y", 0xB000)):
        for sid in set(lines[name].slaves) - {1}:
            assert handle(lines[name].slaves, read(sid, 3, 0))[1]["values"] == [prefix + sid]


def test_bench_profile_serves_every_v1_guanjie_register():
    guanjie = Path(__file__).parents[2] / "firmware/guanjie-scanner/components/guanjie/protocol.h"
    text = guanjie.read_text(encoding="utf-8")
    start = text.index("REGISTERS = {") + len("REGISTERS = {")
    registers = [int(r, 16) for r in text[start : text.index("}", start)].split(",")]
    for line in load_config(BENCH):
        for reg in registers:
            assert handle(line.slaves, read(1, 3, reg))[1]["result"] == "reply"
