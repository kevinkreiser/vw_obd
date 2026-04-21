"""
fuel_pump_monitor — OBD/UDS over raw CAN: fuel pressure, trims, and VW UDS
data identifiers (e.g. LPFP duty) when the engine ECU exposes them.

Usage (SocketCAN)::

  uv run fuel-monitor --can-channel can0
  uv run fuel-monitor --can-channel can0 --once
"""

from __future__ import annotations

import argparse
import time
from typing import Optional

from vw_obd.cli_common import add_can_args, can_extra_from_namespace, can_link_from_args
from vw_obd.obd_isotp import (
    collect_mode1,
    uds_read_data_by_id,
)
from vw_obd.transport import IsoTpSession, open_bus


# VW/Audi: low-pressure fuel pump duty — UDS 0x22, DID 0xC006 (1 byte, scaling below).
# HPFP target: DID 0x1173 (2 bytes, bar×10) — if ECU does not have it, read returns None.
LPFP_DID = 0xC006
HPFP_TARGET_DID = 0x1173


def _lpfp_duty_pct(data: bytes) -> Optional[float]:
    if not data or len(data) < 1:
        return None
    raw = data[0]
    return raw * 0.390625  # VAG convention for this DID on many calibrations


def _hpfp_target_bar(data: bytes) -> Optional[float]:
    if len(data) < 2:
        return None
    v = int.from_bytes(data[0:2], "big", signed=False)
    return v / 10.0


def interpret_duty(duty_pct: float) -> str:
    if duty_pct < 50:
        return "OK — pump load is normal"
    if duty_pct < 70:
        return "ELEVATED — monitor; avoid running the tank very low"
    if duty_pct < 85:
        return "HIGH — likely degraded or tank is low; plan inspection"
    return "CRITICAL — near maximum demand; service likely needed"


def print_snapshot(s: IsoTpSession) -> None:
    t = time.strftime("%H:%M:%S")
    print(f"\n{'─' * 60}\n  Timestamp: {t}")

    snap = collect_mode1(s)
    if snap.load_pct is not None:
        print(f"  Engine load:              {snap.load_pct:.1f} %")
    if snap.rpm is not None:
        print(f"  RPM:                      {snap.rpm:.0f}")
    if snap.coolant_c is not None:
        print(f"  Coolant:                  {snap.coolant_c:.0f} °C")
    if snap.fuel_pressure_gauge_kpa is not None:
        print(f"  Fuel press. (OBD 0x0A):  {snap.fuel_pressure_gauge_kpa:.0f} kPa (gauge, low side)")
    if snap.rail_relatve_kpa is not None:
        print(f"  Rail (rel.):              {snap.rail_relatve_kpa:.1f} kPa")
    if snap.rail_abs_kpa is not None:
        print(f"  Rail (abs):               {snap.rail_abs_kpa:.1f} kPa (high side)")
    if snap.stft_pct is not None:
        print(f"  STFT B1:                  {snap.stft_pct:+.1f} %  (high + means ECU is adding fuel)")
    if snap.ltft_pct is not None:
        print(f"  LTFT B1:                  {snap.ltft_pct:+.1f} %")

    print()
    d = uds_read_data_by_id(s, LPFP_DID, timeout=2.0)
    if d is None:
        print("  LPFP duty:                (no 0x22 0xC006 response; wrong ECU/IDs or ECU does not map this DID)")
    else:
        pct = _lpfp_duty_pct(d)
        if pct is not None:
            print(f"  LPFP duty:                {pct:.1f} %")
            print(f"  LPFP note:                {interpret_duty(pct)}")

    t2 = uds_read_data_by_id(s, HPFP_TARGET_DID, timeout=2.0)
    if t2 is not None:
        b = _hpfp_target_bar(t2)
        if b is not None:
            print(f"  HPFP target rail:         {b:.1f} bar (0x{HPFP_TARGET_DID:04X} — if supported)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="VW/MQB fuel + LPFP UDS over raw CAN (ISO-TP).",
    )
    add_can_args(parser)
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Polling interval in seconds. Default: 2.0",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="One snapshot, then exit.",
    )
    args = parser.parse_args()
    link = can_link_from_args(args)
    extra = can_extra_from_namespace(args)
    bus = open_bus(link, **extra)
    s = IsoTpSession(bus, tx_id=args.tx_id, rx_id=args.rx_id)
    try:
        s.start()
        print("ISO-TP session started.")
        print(f"  {link.interface} {link.channel!r}  @ {link.bitrate}  IDs 0x{args.tx_id:03X}/0x{args.rx_id:03X}")
        print("Ignition ON, engine running recommended for real LPFP/rail data.\n")
        if args.once:
            print_snapshot(s)
        else:
            print(f"Every {args.interval} s (Ctrl+C to stop). LPFP <50% warm idle ≈ healthy, >80% ≈ straining.\n")
            while True:
                print_snapshot(s)
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.\n")
    finally:
        s.stop()
        bus.shutdown()


if __name__ == "__main__":
    main()
