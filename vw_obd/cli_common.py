"""
Shared command-line options for raw CAN (python-can) access.
"""

from __future__ import annotations

import argparse

from vw_obd.transport import CanLinkConfig


def add_can_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--can-interface",
        default="socketcan",
        help="python-can bus backend (e.g. socketcan, slcan, pcan, usb2can). Default: socketcan",
    )
    p.add_argument(
        "--can-channel",
        default="can0",
        help="Bus channel, e.g. can0, or a serial path for SLCAN (e.g. /dev/ttyACM0).",
    )
    p.add_argument(
        "--bitrate",
        type=int,
        default=500_000,
        help="CAN bit rate in Hz. VAG OBD is usually 500 kbit/s. Default: 500000",
    )
    p.add_argument(
        "--tx-id",
        type=lambda x: int(x, 0),
        default=0x7E0,
        help="Tester->ECU CAN ID (11-bit, hex). Default: 0x7E0",
    )
    p.add_argument(
        "--rx-id",
        type=lambda x: int(x, 0),
        default=0x7E8,
        help="ECU->tester CAN ID (11-bit, hex). Default: 0x7E8",
    )
    p.add_argument(
        "--slcan-baud",
        type=int,
        default=None,
        metavar="BPS",
        help="For interface 'slcan': serial baud rate to the adapter (e.g. 115200, 1_000_000).",
    )


def can_link_from_args(ns: argparse.Namespace) -> CanLinkConfig:
    return CanLinkConfig(
        interface=ns.can_interface,
        channel=ns.can_channel,
        bitrate=ns.bitrate,
    )


def can_extra_from_namespace(ns: argparse.Namespace) -> dict:
    """Extra kwargs for ``python-can`` (e.g. SLCAN serial speed)."""
    d: dict = {}
    if getattr(ns, "slcan_baud", None) is not None:
        d["ttyBaudrate"] = ns.slcan_baud
    return d
