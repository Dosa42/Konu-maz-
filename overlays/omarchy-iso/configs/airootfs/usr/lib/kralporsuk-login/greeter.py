"""Native GTK4 login with read-only, live USB descriptor enumeration."""

import json
import os
from pathlib import Path
import socket
import sys
import threading

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk
from usb_devices import display_text, scan_devices


class LoginWindow(Gtk.ApplicationWindow):
    def __init__(self, application, channel):
        super().__init__(application=application, title="kralporsuk")
        self.channel = channel
        self.busy = False
        self.usb_busy = False
        self.usb_snapshot = None
        self.set_decorated(False)
        self.set_deletable(False)
        # A closed window never means authentication succeeded. The parent
        # requires its own successful hash verification before any session.
        self.connect("close-request", lambda *_: True)
        self.fullscreen()

        css = Gtk.CssProvider()
        css.load_from_data(b"""
            window { background: #111720; color: #edf3f8; }
            .login-card { background: #1b2532; border-radius: 18px; padding: 30px; }
            .title { font-size: 32px; font-weight: 700; }
            .subtitle { color: #c2cbd6; }
            .error { color: #ffb6a8; }
            .usb-row { padding: 9px; border-bottom: 1px solid #38475b; }
            button { padding: 10px 18px; }
            entry { padding: 10px; font-size: 18px; }
        """)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        outer.set_margin_top(24)
        outer.set_margin_bottom(24)
        outer.set_margin_start(32)
        outer.set_margin_end(32)
        outer.set_halign(Gtk.Align.CENTER)
        outer.set_valign(Gtk.Align.CENTER)
        outer.set_size_request(660, -1)
        outer.add_css_class("login-card")
        # Keep the complete form reachable on smaller installer displays too.
        page = Gtk.ScrolledWindow()
        page.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        page.set_child(outer)
        self.set_child(page)

        title = Gtk.Label(label="kralporsuk")
        title.add_css_class("title")
        outer.append(title)
        mode = os.environ.get("KRALPORSUK_LOGIN_MODE", "")
        subtitle = Gtk.Label(label={
            "live": "Meld aan om de installer te openen.",
            "installed": "Meld aan om de desktop te openen.",
        }.get(mode, "De loginconfiguratie vereist aandacht."))
        subtitle.add_css_class("subtitle")
        outer.append(subtitle)

        self.password = Gtk.PasswordEntry()
        self.password.set_show_peek_icon(False)
        self.password.set_hexpand(True)
        self.password.set_property("placeholder-text", "Wachtwoord")
        self.password.connect("activate", self.authenticate)
        outer.append(self.password)
        self.login = Gtk.Button(label="Aanmelden")
        self.login.add_css_class("suggested-action")
        self.login.connect("clicked", self.authenticate)
        outer.append(self.login)
        self.status = Gtk.Label(label=os.environ.get("KRALPORSUK_LOGIN_ERROR", ""))
        self.status.set_wrap(True)
        self.status.add_css_class("error")
        self.status.set_max_width_chars(72)
        outer.append(self.status)

        usb_title = Gtk.Label(label="USB-apparaten · live uitlezing")
        usb_title.set_xalign(0)
        outer.append(usb_title)
        self.usb_status = Gtk.Label(label="USB-bus wordt gelezen…")
        self.usb_status.set_xalign(0)
        self.usb_status.set_wrap(True)
        self.usb_status.set_max_width_chars(76)
        outer.append(self.usb_status)
        self.usb_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_height(180)
        scroll.set_max_content_height(280)
        scroll.set_propagate_natural_height(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(self.usb_list)
        outer.append(scroll)
        explanation = Gtk.Label(label="USB is vóór aanmelden beschikbaar. Apparaatgegevens worden gelezen; USB-aanmelding is nog niet ingesteld.")
        explanation.add_css_class("subtitle")
        explanation.set_wrap(True)
        explanation.set_max_width_chars(76)
        outer.append(explanation)

        power = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        power.set_halign(Gtk.Align.CENTER)
        self.power_buttons = []
        for label, action in (("Opnieuw starten", "reboot"), ("Uitschakelen", "poweroff")):
            button = Gtk.Button(label=label)
            button.connect("clicked", lambda _button, command=action: self.request({"action": command}))
            power.append(button)
            self.power_buttons.append(button)
        outer.append(power)
        self.password.grab_focus()
        self.request({"action": "check"})
        self.refresh_usb()
        GLib.timeout_add_seconds(1, self.refresh_usb)

    def set_busy(self, busy):
        self.busy = busy
        self.login.set_sensitive(not busy)
        self.password.set_sensitive(not busy)
        for button in self.power_buttons:
            button.set_sensitive(not busy)

    def authenticate(self, *_):
        if self.busy:
            return
        password = self.password.get_text()
        self.password.set_text("")
        self.request({"action": "password", "password": password})

    def request(self, payload):
        if self.busy:
            return
        self.set_busy(True)

        def exchange():
            try:
                packet = json.dumps(payload).encode("utf-8")
                payload.clear()
                self.channel.send(packet)
                packet = b""
                response = self.channel.recv(8193)
                if not response or len(response) > 8192:
                    raise ValueError("invalid response")
                result = json.loads(response)
                if not isinstance(result, dict) or result.get("result") not in {
                    "ready", "authenticated", "rejected", "error", "power-requested",
                }:
                    raise ValueError("invalid response")
                GLib.idle_add(self.completed, result)
            except (OSError, ValueError, UnicodeError):
                GLib.idle_add(self.channel_failed)

        threading.Thread(target=exchange, daemon=True).start()

    def completed(self, response):
        self.set_busy(False)
        result = response["result"]
        if result in {"authenticated", "power-requested"}:
            self.password.set_text("")
            self.get_application().exit_status = 0
            self.get_application().quit()
        elif result != "ready":
            self.status.set_text(display_text(response.get("message", "Aanmelden is mislukt.")))
        self.password.grab_focus()
        return GLib.SOURCE_REMOVE

    def channel_failed(self):
        self.status.set_text("Het interne loginkanaal is onderbroken. De login wordt opnieuw gestart.")
        self.set_busy(True)
        GLib.timeout_add_seconds(4, self.failed_exit)
        return GLib.SOURCE_REMOVE

    def failed_exit(self):
        self.get_application().exit_status = 1
        self.get_application().quit()
        return GLib.SOURCE_REMOVE

    def refresh_usb(self):
        if self.usb_busy:
            return GLib.SOURCE_CONTINUE
        self.usb_busy = True

        def scan():
            try:
                result = scan_devices()
            except Exception:
                result = {"devices": [], "errors": ["USB-uitlezing is mislukt."]}
            GLib.idle_add(self.show_usb, result)

        threading.Thread(target=scan, daemon=True).start()
        return GLib.SOURCE_CONTINUE

    def show_usb(self, result):
        self.usb_busy = False
        if result == self.usb_snapshot:
            return GLib.SOURCE_REMOVE
        self.usb_snapshot = result
        child = self.usb_list.get_first_child()
        while child is not None:
            following = child.get_next_sibling()
            self.usb_list.remove(child)
            child = following
        devices = result["devices"]
        physical = sum(not device["is_root_hub"] for device in devices)
        errors = result["errors"]
        self.usb_status.set_text(" · ".join(display_text(error) for error in errors) if errors else f"{physical} aangesloten USB-apparaten · {len(devices) - physical} root-hubs")
        for device in devices:
            name = device.get("product") or device.get("manufacturer") or device["name"]
            vendor = device.get("vendor_id") or "????"
            product = device.get("product_id") or "????"
            authorization = {"1": "actief", "0": "niet geautoriseerd"}.get(device.get("authorized"), "status onbekend")
            details = [f"{name} — {vendor}:{product}", f"{device['name']} · {authorization} · {device['descriptor_bytes']} descriptorbytes gelezen"]
            if device.get("serial"):
                details.append(f"Serienummer: {device['serial']}")
            details.extend(device["errors"])
            label = Gtk.Label()
            # USB-supplied strings are untrusted data, never GTK markup.
            label.set_text("\n".join(display_text(line, limit=512) for line in details))
            label.set_xalign(0)
            label.set_wrap(True)
            label.set_max_width_chars(76)
            label.add_css_class("usb-row")
            self.usb_list.append(label)
        return GLib.SOURCE_REMOVE


class LoginApplication(Gtk.Application):
    def __init__(self, channel):
        super().__init__(application_id="local.kralporsuk.Login", flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.channel = channel
        self.exit_status = 1

    def do_activate(self):
        window = self.get_active_window()
        if window is None:
            window = LoginWindow(self, self.channel)
        window.present()


def main():
    try:
        fd = int(os.environ.pop("KRALPORSUK_AUTH_FD"))
        channel = socket.socket(fileno=fd)
        channel.set_inheritable(False)
        channel.settimeout(30)
    except (KeyError, ValueError, OSError):
        print("Geen geldig intern loginkanaal.", file=sys.stderr)
        return 1
    with channel:
        application = LoginApplication(channel)
        status = application.run([])
        return status if status else application.exit_status


if __name__ == "__main__":
    raise SystemExit(main())
