"""
OBD-II (J1979) and simple UDS read-by-ID helpers on top of ISO-TP.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from vw_obd.transport import IsoTpSession

# --- DTC: same algorithm as python-obd decoders.parse_dtc (J2012) ---


def dtc_from_two_bytes(b0: int, b1: int) -> str:
    dtc = ["P", "C", "B", "U"][b0 >> 6]
    dtc += str((b0 >> 4) & 0b0011)
    hx = f"{b0:02X}{b1:02X}"
    dtc += hx[1:4]
    return dtc


def parse_obd_dtc_list(resp: bytearray) -> List[str]:
    """
    After ISO-TP reassembly, *resp* is the OBD response body (first byte
    0x43 or 0x47, not counting PCI).
    """
    if len(resp) < 2:
        return []
    service = resp[0]
    if service not in (0x43, 0x47):
        return []
    count = resp[1]
    # SAE: count = number of DTCs, each 2 bytes
    body = resp[2 : 2 + 2 * count]
    if len(body) < 2 * count:
        return []
    out: List[str] = []
    for i in range(0, len(body), 2):
        b0, b1 = body[i], body[i + 1]
        if (b0, b1) == (0, 0):
            continue
        out.append(dtc_from_two_bytes(b0, b1))
    return out


def is_negative_uds(data: bytearray) -> bool:
    return len(data) >= 3 and data[0] == 0x7F


# --- OBD Mode 0x01 (show current data) ---

def _mode1_req(pid: int) -> bytes:
    return bytes([0x01, pid & 0xFF])


def _expect_mode1(resp: Optional[bytearray], pid: int) -> Optional[bytearray]:
    if resp is None or len(resp) < 3:
        return None
    if resp[0] == 0x7F:
        return None
    if resp[0] != 0x41 or resp[1] != (pid & 0xFF):
        return None
    return resp[2:]


# --- Pint removed: plain floats for display ---

def uas2_kpa_019(data: bytes) -> float:
    """UAS 0x19: two byte unsigned * 0.079 kPa (rail relative)."""
    v = int.from_bytes(data[0:2], "big", signed=False)
    return v * 0.079


def uas2_kpa_01B(data: bytes) -> float:
    """UAS 0x1B: two byte unsigned * 10 kPa (rail direct / abs)."""
    v = int.from_bytes(data[0:2], "big", signed=False)
    return v * 10.0


@dataclass
class Mode1Snapshot:
    load_pct: Optional[float]
    rpm: Optional[float]
    coolant_c: Optional[float]
    fuel_pressure_gauge_kpa: Optional[float]
    rail_relatve_kpa: Optional[float]
    rail_abs_kpa: Optional[float]
    stft_pct: Optional[float]
    ltft_pct: Optional[float]


def collect_mode1(session: IsoTpSession) -> Mode1Snapshot:
    s = session

    def m1(pid: int) -> Optional[bytes]:
        r = s.request(_mode1_req(pid))
        return _expect_mode1(r, pid)

    load_pct = stft = ltft = None
    d = m1(0x04)
    if d and len(d) >= 1:
        load_pct = d[0] * 100.0 / 255.0

    rpm = None
    d = m1(0x0C)
    if d and len(d) >= 2:
        rpm = ((d[0] * 256) + d[1]) / 4.0

    coolant = None
    d = m1(0x05)
    if d and len(d) >= 1:
        coolant = float(d[0] - 40)

    fp = None
    d = m1(0x0A)
    if d and len(d) >= 1:
        fp = float(d[0] * 3)  # kPa

    rrel = rabs = None
    d = m1(0x22)
    if d and len(d) >= 2:
        rrel = uas2_kpa_019(bytes(d[0:2]))
    d = m1(0x23)
    if d and len(d) >= 2:
        rabs = uas2_kpa_01B(bytes(d[0:2]))
    d = m1(0x59)  # fuel rail abs (alternate naming in some ECUs)
    if d and len(d) >= 2 and rabs is None:
        rabs = uas2_kpa_01B(bytes(d[0:2]))

    d = m1(0x06)
    if d and len(d) >= 1:
        stft = (d[0] - 128) * 100.0 / 128.0
    d = m1(0x07)
    if d and len(d) >= 1:
        ltft = (d[0] - 128) * 100.0 / 128.0

    return Mode1Snapshot(
        load_pct=load_pct,
        rpm=rpm,
        coolant_c=coolant,
        fuel_pressure_gauge_kpa=fp,
        rail_relatve_kpa=rrel,
        rail_abs_kpa=rabs,
        stft_pct=stft,
        ltft_pct=ltft,
    )


def uds_read_data_by_id(session: IsoTpSession, did: int, timeout: float = 2.0) -> Optional[bytes]:
    """UDS 0x22, positive response 0x62, DID, data…"""
    b0, b1 = (did >> 8) & 0xFF, did & 0xFF
    resp = session.request(bytes([0x22, b0, b1]), timeout=timeout)
    if resp is None:
        return None
    if is_negative_uds(resp) or len(resp) < 3:
        return None
    if resp[0] != 0x62 or resp[1] != b0 or resp[2] != b1:
        return None
    return bytes(resp[3:])


def read_stored_dtcs(session: IsoTpSession) -> List[str]:
    r = session.request(bytes([0x03]), timeout=3.0)
    if r is None:
        return []
    return parse_obd_dtc_list(bytearray(r))


def read_pending_dtcs(session: IsoTpSession) -> List[str]:
    r = session.request(bytes([0x07]), timeout=3.0)
    if r is None:
        return []
    return parse_obd_dtc_list(bytearray(r))


def read_mil_status(session: IsoTpSession) -> Optional[Tuple[bool, int]]:
    """Mode 01 PID 0x01 — MIL and confirmed DTC count (approximate SAE layout)."""
    r = session.request(bytes([0x01, 0x01]), timeout=2.0)
    d = _expect_mode1(r, 0x01)
    if d is None or len(d) < 1:
        return None
    b0 = d[0]
    mil = (b0 & 0x80) != 0
    dtc_c = b0 & 0x7F
    return mil, dtc_c
