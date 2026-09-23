#!/usr/bin/env python3
"""Read USB enumeration data before login, without mounting or executing media.

``scan_devices()`` returns ``{"devices": [record, ...], "errors": [str, ...]}``.
Call it again to get current hotplug state; no devices are cached. Top-level
errors mean the bus could not be enumerated. Individual records carry their own
errors, including unplug races. Missing optional USB strings are ``None``.

The kernel's USB sysfs ABI exposes a device descriptor followed by configuration
descriptors in ``descriptors``. Reads are bounded to 64 KiB; ``descriptor_hex``
contains only the initial 18 bytes. Descriptor/serial data identifies what a
device reports and is not authentication or proof of a cryptographic key.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import struct
import sys
import unicodedata


SYSFS_ROOT = Path("/sys/bus/usb/devices")
MAX_TEXT_BYTES = 4096
MAX_DISPLAY_CHARS = 256
MAX_DESCRIPTOR_BYTES = 65536
DEVICE_NAME = re.compile(r"(?:usb[0-9]+|[0-9]+-[0-9]+(?:\.[0-9]+)*)\Z")


def display_text(value: str, limit: int = MAX_DISPLAY_CHARS) -> str:
    """Remove control, surrogate, bidi-format and line-separator characters."""
    return "".join(
        char for char in value
        if not unicodedata.category(char).startswith("C")
        and unicodedata.category(char) not in ("Zl", "Zp")
    )[:limit].strip()


def _error(path: Path, error: OSError) -> str:
    return display_text(f"{path.name}: {error.strerror or str(error)} (errno={error.errno})")


def _text_attribute(device: Path, name: str, errors: list[str], *, optional: bool = False) -> str | None:
    path = device / name
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_TEXT_BYTES + 1)
    except FileNotFoundError as error:
        if not optional:
            errors.append(_error(path, error))
        return None
    except OSError as error:
        errors.append(_error(path, error))
        return None
    if len(raw) > MAX_TEXT_BYTES:
        errors.append(f"{name}: attribute exceeds {MAX_TEXT_BYTES} bytes; display truncated")
    return display_text(raw[:MAX_TEXT_BYTES].decode("utf-8", errors="replace"))


def _device_descriptor(data: bytes, errors: list[str]) -> dict | None:
    if len(data) < 18:
        errors.append(f"descriptors: short USB device descriptor ({len(data)} of 18 bytes)")
        return None
    if data[0] != 18 or data[1] != 1:
        errors.append(f"descriptors: invalid device descriptor length/type ({data[0]}/{data[1]})")
        return None
    values = struct.unpack("<BBHBBBBHHHBBBB", data[:18])
    names = (
        "length", "descriptor_type", "usb_version_bcd", "device_class",
        "device_subclass", "device_protocol", "max_packet_size_0", "vendor_id",
        "product_id", "device_version_bcd", "manufacturer_string_index",
        "product_string_index", "serial_string_index", "configuration_count",
    )
    return dict(zip(names, values))


def _scan_device(device: Path) -> dict:
    errors: list[str] = []
    record = {
        "name": display_text(device.name),
        "path": display_text(str(device), limit=1024),
        "is_root_hub": device.name.startswith("usb"),
        "vendor_id": None,
        "product_id": None,
        "manufacturer": None,
        "product": None,
        "serial": None,
        "authorized": None,
        "descriptor_bytes": 0,
        "descriptor_truncated": False,
        "descriptor_hex": "",
        "device_descriptor": None,
        "errors": errors,
    }
    try:
        device.stat()  # Follow the normal sysfs bus-to-device symlink.
    except OSError as error:
        errors.append(_error(device, error))
        return record
    for output, attribute in (("vendor_id", "idVendor"), ("product_id", "idProduct")):
        value = _text_attribute(device, attribute, errors)
        if value is not None:
            if re.fullmatch(r"[0-9a-fA-F]{4}", value):
                record[output] = value.lower()
            else:
                errors.append(f"{attribute}: invalid four-digit hexadecimal ID")
    for attribute in ("manufacturer", "product", "serial"):
        record[attribute] = _text_attribute(device, attribute, errors, optional=True)
    authorized = _text_attribute(device, "authorized", errors)
    if authorized in ("0", "1"):
        record["authorized"] = authorized
    elif authorized is not None:
        errors.append("authorized: invalid USB authorization state")
    try:
        with (device / "descriptors").open("rb") as stream:
            data = stream.read(MAX_DESCRIPTOR_BYTES + 1)
    except OSError as error:
        errors.append(_error(device / "descriptors", error))
    else:
        record["descriptor_truncated"] = len(data) > MAX_DESCRIPTOR_BYTES
        data = data[:MAX_DESCRIPTOR_BYTES]
        record["descriptor_bytes"] = len(data)
        record["descriptor_hex"] = data[:18].hex()
        record["device_descriptor"] = _device_descriptor(data, errors)
        if record["descriptor_truncated"]:
            errors.append(f"descriptors: read capped at {MAX_DESCRIPTOR_BYTES} bytes")
        parsed = record["device_descriptor"]
        if parsed is not None:
            for key in ("vendor_id", "product_id"):
                if record[key] is not None and int(record[key], 16) != parsed[key]:
                    errors.append(f"descriptors: {key} differs from sysfs attribute; device may have changed")
    return record


def scan_devices(sysfs_root: Path = SYSFS_ROOT) -> dict:
    """Return JSON-safe current USB records and explicit bus/per-device errors.

    Both ordinary directories and Linux's normal USB device symlinks work.
    USB interface entries (such as ``1-1:1.0``) are not duplicate devices.
    An unreadable bus is distinguishable from a successfully read empty bus.
    """
    root = Path(sysfs_root)
    result: dict = {"devices": [], "errors": []}
    try:
        entries = sorted(root.iterdir(), key=lambda entry: entry.name)
    except OSError as error:
        result["errors"].append(f"USB bus unavailable: {_error(root, error)}")
        return result
    for entry in entries:
        if DEVICE_NAME.fullmatch(entry.name):
            result["devices"].append(_scan_device(entry))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sysfs-root", type=Path, default=SYSFS_ROOT)
    arguments = parser.parse_args()
    result = scan_devices(arguments.sysfs_root)
    json.dump(result, sys.stdout, ensure_ascii=True, indent=2)
    sys.stdout.write("\n")
    return int(bool(result["errors"] or any(record["errors"] for record in result["devices"])))


if __name__ == "__main__":
    raise SystemExit(main())
