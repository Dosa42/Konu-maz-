#!/usr/bin/env python3
"""USB sysfs parsing and hotplug regressions, not physical hardware tests."""

import errno
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "overlays/omarchy-iso/configs/airootfs/usr/lib/kralporsuk-login/usb_devices.py"
SPEC = importlib.util.spec_from_file_location("usb_devices", MODULE_PATH)
usb = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(usb)


class USBDeviceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="usb-sysfs-regression-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.bus = self.base / "bus/usb/devices"
        self.bus.mkdir(parents=True)

    def device(self, name="1-1", *, symlink=False):
        path = self.base / "devices" / name if symlink else self.bus / name
        path.mkdir(parents=True)
        if symlink:
            (self.bus / name).symlink_to(path, target_is_directory=True)
        for attr, value in {
            "idVendor": "1234\n", "idProduct": "abcd\n", "authorized": "1\n",
            "manufacturer": "USB vendor\n", "product": "USB token\n", "serial": "serial-1\n",
        }.items():
            (path / attr).write_text(value)
        descriptor = struct.pack("<BBHBBBBHHHBBBB", 18, 1, 0x200, 0, 0, 0, 64, 0x1234, 0xabcd, 0x100, 1, 2, 3, 1)
        (path / "descriptors").write_bytes(descriptor + b"\x09\x02\x09\x00\x00\x01\x00\x80\x32")
        return path

    def test_normal_sysfs_symlink_and_binary_descriptor(self):
        self.device(symlink=True)
        (self.bus / "1-1:1.0").mkdir()
        result = usb.scan_devices(self.bus)
        self.assertEqual(result["errors"], [])
        self.assertEqual(len(result["devices"]), 1)
        device = result["devices"][0]
        self.assertEqual(device["errors"], [])
        self.assertEqual(device["vendor_id"], "1234")
        self.assertEqual(device["product_id"], "abcd")
        self.assertEqual(device["serial"], "serial-1")
        self.assertEqual(device["authorized"], "1")
        self.assertEqual(device["device_descriptor"]["product_id"], 0xabcd)
        self.assertEqual(device["descriptor_bytes"], 27)
        self.assertEqual(len(device["descriptor_hex"]), 36)
        self.assertFalse(device["descriptor_truncated"])
        self.assertEqual(json.loads(json.dumps(result)), result)

    def test_hotplug_add_remove_and_disappeared_symlink(self):
        self.assertEqual(usb.scan_devices(self.bus), {"devices": [], "errors": []})
        path = self.device(symlink=True)
        self.assertEqual(len(usb.scan_devices(self.bus)["devices"]), 1)
        shutil.rmtree(path)
        stale = usb.scan_devices(self.bus)["devices"][0]
        self.assertTrue(stale["errors"])
        self.assertIsNone(stale["vendor_id"])
        (self.bus / "1-1").unlink()
        self.assertEqual(usb.scan_devices(self.bus), {"devices": [], "errors": []})

    def test_unavailable_bus_is_explicit_not_empty_success(self):
        result = usb.scan_devices(self.base / "missing")
        self.assertEqual(result["devices"], [])
        self.assertIn("USB bus unavailable", result["errors"][0])
        with patch.object(Path, "iterdir", side_effect=PermissionError(errno.EACCES, "Permission denied")):
            result = usb.scan_devices(self.bus)
        self.assertTrue(result["errors"])

    def test_unreadable_descriptor_does_not_hide_device(self):
        self.device()
        original_open = Path.open

        def deny_descriptor(path, *args, **kwargs):
            if path.name == "descriptors":
                raise PermissionError(errno.EACCES, "Permission denied")
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", deny_descriptor):
            record = usb.scan_devices(self.bus)["devices"][0]
        self.assertEqual(record["product"], "USB token")
        self.assertTrue(any("descriptors: Permission denied" in error for error in record["errors"]))
        self.assertIsNone(record["device_descriptor"])

    def test_malformed_descriptor_and_optional_missing_strings(self):
        path = self.device()
        for attribute in ("serial", "manufacturer", "product"):
            (path / attribute).unlink()
        (path / "descriptors").write_bytes(b"\x12\x01\x00")
        record = usb.scan_devices(self.bus)["devices"][0]
        self.assertIsNone(record["serial"])
        self.assertEqual(len(record["errors"]), 1)
        self.assertIn("short USB device descriptor", record["errors"][0])
        (path / "descriptors").write_bytes(bytes([17, 1]) + b"\0" * 16)
        record = usb.scan_devices(self.bus)["devices"][0]
        self.assertIsNone(record["device_descriptor"])
        self.assertIn("invalid device descriptor length/type", record["errors"][0])

    def test_control_escape_and_bidi_data_are_not_rendered_as_control(self):
        path = self.device()
        (path / "product").write_bytes(b"evil\x1b[2J\x00\n\r\t" + "\u202e\u2028".encode() + b"X" * 5000)
        record = usb.scan_devices(self.bus)["devices"][0]
        self.assertEqual(len(record["product"]), usb.MAX_DISPLAY_CHARS)
        for control in ("\x1b", "\x00", "\n", "\r", "\t", "\u202e", "\u2028"):
            self.assertNotIn(control, record["product"])
        self.assertTrue(any("attribute exceeds" in error for error in record["errors"]))

    def test_large_descriptor_is_bounded_and_truncation_visible(self):
        path = self.device()
        (path / "descriptors").write_bytes((path / "descriptors").read_bytes() + b"\0" * 100000)
        record = usb.scan_devices(self.bus)["devices"][0]
        self.assertTrue(record["descriptor_truncated"])
        self.assertEqual(record["descriptor_bytes"], usb.MAX_DESCRIPTOR_BYTES)
        self.assertEqual(len(record["descriptor_hex"]), 36)
        self.assertIsNotNone(record["device_descriptor"])
        self.assertTrue(any("read capped" in error for error in record["errors"]))

    def test_invalid_ids_and_mismatched_descriptor_are_visible(self):
        path = self.device()
        (path / "idVendor").write_text("not-a-vendor\n")
        (path / "idProduct").write_text("ffff\n")
        (path / "authorized").write_text("no\n")
        record = usb.scan_devices(self.bus)["devices"][0]
        self.assertIsNone(record["vendor_id"])
        self.assertIsNone(record["authorized"])
        self.assertTrue(any("invalid four-digit" in error for error in record["errors"]))
        self.assertTrue(any("product_id differs" in error for error in record["errors"]))
        self.assertTrue(any("invalid USB authorization state" in error for error in record["errors"]))


if __name__ == "__main__":
    unittest.main()
