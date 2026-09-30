"""Physical provider bench test. Does not install or emulate HA services."""

import argparse
import asyncio
import datetime
import json

from bridge_runtime import (
    ESPHomeGateway,
    ESPHomeGatewayProvider,
    GatewayProviderError,
    ProbeType,
    ScanRequest,
)


async def run(args):
    gateway = ESPHomeGateway(args.host, args.mac)
    provider = ESPHomeGatewayProvider([gateway])
    request = ScanRequest(
        provider="esphome",
        gateway_id=gateway.gateway_id,
        start_id=args.start,
        end_id=args.end,
        probe_type=ProbeType.HOLDING_REGISTER,
        register_address=args.register,
        register_count=1,
        timeout_ms=700,
        retries=0,
        inter_request_delay_ms=250,
        pause_normal_polling=True,
        safety_confirmed=args.confirm_physical,
    )
    results = []

    def emit(result):
        results.append(result.as_dict())
        print(json.dumps(result.as_dict()), flush=True)

    report = {
        "time_utc": datetime.datetime.now(datetime.UTC).isoformat(),
        "test_layer": "provider-direct, not HA services",
        "simulated": False,
        "gateway_id": gateway.gateway_id,
        "start_id": args.start,
        "end_id": args.end,
        "register_address": args.register,
        "results": results,
    }
    try:
        await provider.run_scan(request, emit, lambda: False)
        report["status"] = "completed"
    except (GatewayProviderError, ValueError) as exc:
        report["status"] = "failed"
        report["error"] = str(exc)
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "completed" else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--mac", required=True)
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=1)
    parser.add_argument("--register", type=lambda s: int(s, 0), default=0x6201)
    parser.add_argument("--confirm-physical", action="store_true", required=True)
    raise SystemExit(asyncio.run(run(parser.parse_args())))
