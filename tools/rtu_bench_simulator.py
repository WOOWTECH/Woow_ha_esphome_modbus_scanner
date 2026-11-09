"""Modbus RTU slave simulator for the #16 bench (USB-to-RS-485 converters, no real devices).

One process serves several serial ports. Each port is one RS-485 line wired to one Gateway
and answers for the slave IDs its config lists; every other ID stays silent, as an empty
address does on a real bus. Every request is written to one log, so Probes, Pausable Poller
reads and their pauses can be compared on one timeline.

    python tools/rtu_bench_simulator.py tools/bench_profiles/bench.json \
        --port X=COM5 --port Y=COM6 --log bench.log

Supported: FC03 / FC04 reads and FC06 writes (the v1 Guanjie firmware writes on user
commands). Other function codes get exception 01. Needs pyserial only to open ports; the
request handling below is pure and unit-tested.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import datetime
import json
from pathlib import Path
import sys
import threading

COUNTER = "counter"
READ_FUNCTIONS = {3: "holding", 4: "input"}


def crc16(data: bytes) -> bytes:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc.to_bytes(2, "little")


def with_crc(body: bytes) -> bytes:
    return body + crc16(body)


@dataclass
class Register:
    value: int = 0
    counter: bool = False

    def read(self) -> int:
        value = self.value
        if self.counter:
            self.value = (self.value + 1) & 0xFFFF
        return value


@dataclass
class Slave:
    holding: dict[int, Register] = field(default_factory=dict)
    input: dict[int, Register] = field(default_factory=dict)


def _register(raw) -> Register:
    if raw == COUNTER:
        return Register(0, counter=True)
    if isinstance(raw, int) and not isinstance(raw, bool) and 0 <= raw <= 0xFFFF:
        return Register(raw)
    raise ValueError(f"register value must be 0-65535 or {COUNTER!r}, got {raw!r}")


def _address(raw: str) -> int:
    value = int(raw, 0)
    if not 0 <= value <= 0xFFFF:
        raise ValueError(f"register address out of range: {raw}")
    return value


def build_slaves(raw: dict) -> dict[int, Slave]:
    slaves = {}
    for slave_id, tables in raw.items():
        sid = int(slave_id)
        if not 1 <= sid <= 247:
            raise ValueError(f"slave id must be 1-247, got {slave_id}")
        unknown = set(tables) - {"holding", "input"}
        if unknown:
            raise ValueError(f"slave {sid}: unknown tables {sorted(unknown)}")
        slaves[sid] = Slave(
            holding={_address(a): _register(v) for a, v in tables.get("holding", {}).items()},
            input={_address(a): _register(v) for a, v in tables.get("input", {}).items()},
        )
    return slaves


def request_length(buffer: bytes) -> int | None:
    """Length of the request frame at the start of buffer, or None while unknown."""
    if len(buffer) < 2:
        return None
    function = buffer[1]
    if function in (3, 4, 6):
        return 8
    if function == 16:
        return 9 + buffer[6] if len(buffer) >= 7 else None
    return 0  # unknown function code: not a frame start


class FrameBuffer:
    """Splits the byte stream from the master into CRC-valid request frames.

    Requests have lengths fixed by their function code, so frames are cut by length and
    CRC rather than by the 3.5-character gap, which USB converters and Windows timers do
    not preserve. A CRC failure or an unsupported function code drops one byte and
    resyncs; the Gateway only sends FC03, FC04 and FC06.
    """

    def __init__(self):
        self._buffer = b""
        self.resyncs = 0

    def feed(self, data: bytes) -> list[bytes]:
        self._buffer += data
        frames = []
        while True:
            length = request_length(self._buffer)
            if length is None or len(self._buffer) < length:
                break
            if length == 0:
                self.resyncs += 1
                self._buffer = self._buffer[1:]
                continue
            frame = self._buffer[:length]
            if crc16(frame[:-2]) == frame[-2:]:
                frames.append(frame)
                self._buffer = self._buffer[length:]
            else:
                self.resyncs += 1
                self._buffer = self._buffer[1:]
        return frames

    def gap(self) -> bytes:
        """Called after a silent interval: discard and return a partial frame."""
        rest, self._buffer = self._buffer, b""
        return rest


def handle(slaves: dict[int, Slave], frame: bytes) -> tuple[bytes | None, dict]:
    """Answer one request frame. Returns (reply or None for silence, log fields)."""
    slave_id, function = frame[0], frame[1] if len(frame) > 1 else None
    entry = {"slave": slave_id, "fc": function}
    if len(frame) < 4 or crc16(frame[:-2]) != frame[-2:]:
        entry.update(result="unparsed", raw=frame.hex())
        return None, entry
    slave = slaves.get(slave_id)
    if slave is None:
        entry["result"] = "broadcast" if slave_id == 0 else "silent"
        return None, entry

    def exception(code: int):
        entry.update(result="exception", code=code)
        return with_crc(bytes([slave_id, function | 0x80, code])), entry

    if function in READ_FUNCTIONS:
        address = int.from_bytes(frame[2:4], "big")
        count = int.from_bytes(frame[4:6], "big")
        entry.update(addr=address, count=count)
        if not 1 <= count <= 125:
            return exception(3)
        table = getattr(slave, READ_FUNCTIONS[function])
        if any(address + i not in table for i in range(count)):
            return exception(2)
        values = [table[address + i].read() for i in range(count)]
        entry.update(result="reply", values=values)
        payload = b"".join(v.to_bytes(2, "big") for v in values)
        return with_crc(bytes([slave_id, function, 2 * count]) + payload), entry
    if function == 6:
        address = int.from_bytes(frame[2:4], "big")
        value = int.from_bytes(frame[4:6], "big")
        entry.update(addr=address, value=value)
        register = slave.holding.get(address)
        if register is None:
            return exception(2)
        register.value = value
        entry["result"] = "written"
        return frame, entry
    return exception(1)


@dataclass
class Line:
    name: str
    baudrate: int
    parity: str
    stopbits: int
    slaves: dict[int, Slave]


def load_config(path: Path) -> list[Line]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    lines = []
    for name, spec in raw["lines"].items():
        parity = spec.get("parity", "N")
        if parity not in ("N", "E", "O"):
            raise ValueError(f"line {name}: parity must be N, E or O")
        lines.append(
            Line(
                name=name,
                baudrate=int(spec["baudrate"]),
                parity=parity,
                stopbits=int(spec.get("stopbits", 1)),
                slaves=build_slaves(spec["slaves"]),
            )
        )
    return lines


class Log:
    def __init__(self, path: Path | None):
        self._lock = threading.Lock()
        self._file = path.open("a", encoding="utf-8") if path else None

    def write(self, line: str, entry: dict):
        stamp = datetime.datetime.now().isoformat(timespec="milliseconds")
        text = json.dumps({"ts": stamp, "line": line, **entry}, ensure_ascii=False)
        with self._lock:
            print(text, flush=True)
            if self._file:
                self._file.write(text + "\n")
                self._file.flush()


def serve(line: Line, port: str, log: Log, stop: threading.Event):
    import serial  # pyserial; imported here so the pure logic above needs no dependency

    char_s = 11 / line.baudrate
    with serial.Serial(
        port,
        line.baudrate,
        parity=line.parity,
        stopbits=line.stopbits,
        bytesize=8,
        timeout=max(0.02, 3.5 * char_s),
    ) as conn:
        log.write(
            line.name,
            {
                "result": "open",
                "port": port,
                "baudrate": line.baudrate,
                "parity": line.parity,
                "stopbits": line.stopbits,
                "slaves": sorted(line.slaves),
            },
        )
        frames = FrameBuffer()
        while not stop.is_set():
            data = conn.read(256)
            if not data:
                rest = frames.gap()
                if rest:
                    log.write(line.name, {"result": "discarded", "raw": rest.hex()})
                continue
            for frame in frames.feed(data):
                reply, entry = handle(line.slaves, frame)
                if reply:
                    conn.write(reply)
                log.write(line.name, entry)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("config", type=Path)
    parser.add_argument(
        "--port",
        action="append",
        required=True,
        metavar="LINE=COMx",
        help="serial port for one line of the config; repeat per line",
    )
    parser.add_argument("--log", type=Path, help="also append JSON lines to this file")
    args = parser.parse_args(argv)
    lines = {line.name: line for line in load_config(args.config)}
    ports = dict(item.split("=", 1) for item in args.port)
    unknown = set(ports) - set(lines)
    if unknown:
        parser.error(f"no such line in config: {', '.join(sorted(unknown))}")
    log = Log(args.log)
    stop = threading.Event()
    threads = [
        threading.Thread(target=serve, args=(lines[name], port, log, stop), daemon=True)
        for name, port in ports.items()
    ]
    for thread in threads:
        thread.start()
    try:
        while any(t.is_alive() for t in threads):
            for thread in threads:
                thread.join(0.5)
    except KeyboardInterrupt:
        stop.set()
    return 0


if __name__ == "__main__":
    sys.exit(main())
