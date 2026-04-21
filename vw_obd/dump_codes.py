"""
dump_codes — Read OBD-II DTCs over raw CAN (ISO-TP) / SocketCAN or SLCAN.

Example (SocketCAN)::

  sudo ip link set can0 up type can bitrate 500000
  uv run dump-codes --can-channel can0

SLCAN (serial adapter; bring up is often done with ``slcand`` or use slcan
interface directly)::

  uv run dump-codes --can-interface slcan --can-channel /dev/ttyACM0 --slcan-baud 115200
"""

from __future__ import annotations

import argparse

from vw_obd.cli_common import add_can_args, can_extra_from_namespace, can_link_from_args
from vw_obd.obd_isotp import read_mil_status, read_pending_dtcs, read_stored_dtcs
from vw_obd.transport import IsoTpSession, open_bus


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dump OBD-II DTCs via raw CAN/ISO-TP (not ELM327).",
    )
    add_can_args(parser)
    args = parser.parse_args()
    link = can_link_from_args(args)
    extra = can_extra_from_namespace(args)
    bus = open_bus(link, **extra)
    session = IsoTpSession(bus, tx_id=args.tx_id, rx_id=args.rx_id)
    try:
        session.start()
        print("Connected: ISO-TP on", link.interface, "channel", repr(link.channel))
        print(f"  (IDs 0x{args.tx_id:03X} -> 0x{args.rx_id:03X}, {link.bitrate} bps)\n")
        # --- stored ---
        print("=" * 50)
        print("STORED (CONFIRMED) DTCs  [service 0x03]")
        print("=" * 50)
        codes = read_stored_dtcs(session)
        if not codes:
            print("  None reported.")
        else:
            for c in codes:
                print(f"  {c}")
        # --- pending ---
        print()
        print("=" * 50)
        print("PENDING DTCs  [service 0x07]")
        print("=" * 50)
        pend = read_pending_dtcs(session)
        if not pend:
            print("  None reported.")
        else:
            for c in pend:
                print(f"  {c}")
        # --- MIL (mode 1 PID 1) ---
        print()
        print("=" * 50)
        print("MIL (check engine) — mode 0x01, PID 0x01 (partial decode)")
        print("=" * 50)
        mil = read_mil_status(session)
        if mil is None:
            print("  No response (ECU may not support this over these IDs).")
        else:
            m, n = mil
            print(f"  MIL: {'on' if m else 'off'}  |  DTC count field: {n}")
    finally:
        session.stop()
        bus.shutdown()
    print("\nDone.")


if __name__ == "__main__":
    main()
