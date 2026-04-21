"""
Open a python-can bus and an ISO-TP (ISO 15765) stack for OBD/UDS over CAN.

Typical flow on Linux (SocketCAN):

1. Find your device (some USB–CAN bridges create ``can0``; SLCAN devices may
   use ``/dev/ttyUSB0`` with interface ``slcan``).
2. Bring the link up (SocketCAN)::

     sudo ip link set can0 up type can bitrate 500000

3. Run this project with ``--can-interface socketcan --can-channel can0``.

VW/Audi on the OBD-II port (through the gateway) usually uses 11-bit CAN
IDs 0x7E0 (tester -> ECU) and 0x7E8 (ECU -> tester) at 500 kbit/s.
If your car does not answer, try ``--tx-id`` / ``--rx-id`` from your
wiring/scan-tool logs.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import Any, Generator, Optional

import can
import isotp
from isotp import address as isotp_addr


@dataclass(frozen=True)
class CanLinkConfig:
    """User-facing bus selection (python-can)."""

    interface: str
    """e.g. ``socketcan``, ``slcan``, ``pcan``"""

    channel: str
    """e.g. ``can0`` or ``/dev/ttyUSB0`` (for slcan)"""

    bitrate: int
    """CAN nominal bitrate (Hz), often 500_000 for OBD on VAG passenger cars."""


def open_bus(cfg: CanLinkConfig, **can_kwargs: Any) -> can.BusABC:
    """
    Create a :class:`can.Bus` using the same arguments as ``python-can``'s
    :func:`can.Bus` constructor.
    """
    return can.Bus(
        interface=cfg.interface,
        channel=cfg.channel,
        bitrate=cfg.bitrate,
        **can_kwargs,
    )


class IsoTpSession:
    """
    ISO-TP over CAN for one ECU (single tx/rx ID pair).

    Uses :class:`isotp.CanStack` with the library's built-in background threads
    (``start()`` / ``stop()``), which is the recommended mode for v2 of can-isotp.
    """

    def __init__(
        self,
        bus: can.BusABC,
        tx_id: int = 0x7E0,
        rx_id: int = 0x7E8,
    ) -> None:
        self._bus = bus
        self.tx_id = tx_id
        self.rx_id = rx_id
        addr = isotp.Address(
            isotp_addr.AddressingMode.Normal_11bits,
            txid=tx_id,
            rxid=rx_id,
        )
        # Timings in ms; defaults are often tight on first bring-up of a new interface.
        params: dict[str, Any] = {
            "stmin": 0,
            "tx_data_length": 8,
            "rx_consecutive_frame_timeout": 2000,
            "rx_flowcontrol_timeout": 2000,
        }
        self._stack: isotp.CanStack = isotp.CanStack(
            bus,
            address=addr,
            params=params,
        )
        self._started = False

    @property
    def bus(self) -> can.BusABC:
        return self._bus

    def start(self) -> None:
        if not self._started:
            self._stack.start()
            self._started = True

    def stop(self) -> None:
        if self._started:
            self._stack.stop()
            self._started = False

    @contextlib.contextmanager
    def run(self) -> Generator[None, None, None]:
        self.start()
        try:
            yield
        finally:
            self.stop()

    def request(
        self,
        payload: bytes,
        timeout: float = 2.0,
        target: isotp_addr.TargetAddressType = isotp_addr.TargetAddressType.Physical,
    ) -> Optional[bytearray]:
        """
        Send an ISO-TP message (OBD or UDS raw payload) and wait for one reply.
        """
        if not self._started:
            raise RuntimeError("IsoTpSession is not started; use 'with session.run():' or start()")
        self._stack.send(bytearray(payload), target_address_type=target)
        return self._stack.recv(block=True, timeout=timeout)



@contextlib.contextmanager
def open_isotp_session(
    cfg: CanLinkConfig,
    tx_id: int = 0x7E0,
    rx_id: int = 0x7E8,
    **can_kwargs: Any,
) -> Generator[IsoTpSession, None, None]:
    bus = open_bus(cfg, **can_kwargs)
    s = IsoTpSession(bus, tx_id=tx_id, rx_id=rx_id)
    try:
        with s.run():
            yield s
    finally:
        bus.shutdown()
