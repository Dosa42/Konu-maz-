"""Own authentication, the graphical greeter, and the authenticated session."""

import json
import os
from pathlib import Path
import select
import signal
import socket
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from auth import AuthenticationError, check_backend, read_owned_file, verify_password


CONFIG = Path("/etc/kralporsuk-login.json")
RUNTIME = Path("/run/kralporsuk-login")
MAX_MESSAGE = 8192
SESSION_COMMANDS = {
    "live": ["/usr/local/bin/omarchy-installer-session"],
    "installed": ["/usr/local/bin/kralporsuk-session"],
}
POWER_COMMANDS = {
    "reboot": ["/usr/bin/systemctl", "--no-block", "reboot"],
    "poweroff": ["/usr/bin/systemctl", "--no-block", "poweroff"],
}


def load_mode(path: Path = CONFIG) -> str:
    try:
        config = json.loads(read_owned_file(path, limit=1024))
    except (ValueError, AuthenticationError) as error:
        raise AuthenticationError("De vaste loginconfiguratie ontbreekt of is ongeldig.") from error
    if not isinstance(config, dict) or set(config) != {"mode"} or not isinstance(config["mode"], str) or config["mode"] not in SESSION_COMMANDS:
        raise AuthenticationError("De loginmodus moet uitsluitend live of installed zijn.")
    return config["mode"]


def base_environment() -> dict:
    # A fixed environment keeps user configuration from selecting another
    # compositor, library, Python module, seat backend or startup command.
    return {
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/bin",
        "HOME": "/root",
        "USER": "kralporsuk",
        "LOGNAME": "kralporsuk",
        "SHELL": "/bin/bash",
        "LANG": "en_US.UTF-8",
        "TERM": "linux",
    }


def decode_request(packet: bytes) -> dict:
    if not packet or len(packet) > MAX_MESSAGE:
        raise AuthenticationError("Ongeldig bericht op het interne loginkanaal.")
    try:
        request = json.loads(packet)
    except (ValueError, UnicodeError) as error:
        raise AuthenticationError("Ongeldig bericht op het interne loginkanaal.") from error
    if not isinstance(request, dict) or not isinstance(request.get("action"), str) or request["action"] not in {"check", "password", "reboot", "poweroff"}:
        raise AuthenticationError("Onbekend verzoek op het interne loginkanaal.")
    keys = {"action", "password"} if request["action"] == "password" else {"action"}
    if set(request) != keys:
        raise AuthenticationError("Onverwachte velden op het interne loginkanaal.")
    if request["action"] == "password" and not isinstance(request["password"], str):
        raise AuthenticationError("Ongeldig wachtwoordverzoek.")
    return request


def authenticate_request(request: dict, *, root: Path = Path("/"), configuration_error="") -> dict:
    """Used by the parent process, never by an exit status from the UI."""
    try:
        if configuration_error:
            raise AuthenticationError(configuration_error)
        if request["action"] == "check":
            check_backend(root)
            return {"result": "ready"}
        if request["action"] != "password":
            raise AuthenticationError("Dit verzoek is geen wachtwoordverificatie.")
        if verify_password(request["password"], root):
            return {"result": "authenticated"}
        return {"result": "rejected", "message": "Onjuist wachtwoord."}
    except (AuthenticationError, UnicodeError) as error:
        message = str(error) if isinstance(error, AuthenticationError) else "Ongeldige wachtwoordhash."
        return {"result": "error", "message": message}


def session_authorized(verified: bool, compositor_exit: int) -> bool:
    return verified is True and compositor_exit == 0


def foreground(process_group: int) -> None:
    if os.isatty(0):
        os.tcsetpgrp(0, process_group)


def claim_terminal() -> None:
    # The supervisor is single-threaded. Claim the foreground in the child
    # before exec, preventing a fast installer read from receiving SIGTTIN
    # while the parent is still returning from Popen().
    foreground(os.getpgrp())


def stop_process_group(process: subprocess.Popen) -> None:
    # Children such as seatd/compositor/installer helpers cannot survive a
    # crashed launcher and continue behind the next login screen.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def run_greeter(mode: str | None, error_message: str) -> tuple[bool, bool]:
    parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    environment = base_environment()
    environment.update({
        "HOME": str(RUNTIME / "greeter-home"),
        "XDG_RUNTIME_DIR": str(RUNTIME / "greeter-runtime"),
        "XDG_SESSION_TYPE": "wayland",
        "GDK_BACKEND": "wayland",
        "GTK_A11Y": "none",
        "LIBSEAT_BACKEND": "seatd",
        "KRALPORSUK_AUTH_FD": str(child.fileno()),
        "KRALPORSUK_LOGIN_ERROR": error_message,
        "KRALPORSUK_LOGIN_MODE": mode or "",
    })
    for subdir in ("greeter-home", "greeter-runtime"):
        (RUNTIME / subdir).mkdir(mode=0o700, exist_ok=True)
        (RUNTIME / subdir).chmod(0o700)
    process = None
    verified = False
    power_requested = False
    try:
        # Cage does not enable VT switching. GTK uses Wayland explicitly.
        # Both seatd-launch and Cage inherit the private socket descriptor.
        process = subprocess.Popen(
            ["/usr/bin/seatd-launch", "--", "/usr/bin/cage", "-d", "--",
             "/usr/bin/python", "-I", str(HERE / "greeter.py")],
            pass_fds=(child.fileno(),), env=environment, process_group=0,
            preexec_fn=claim_terminal if os.isatty(0) else None,
        )
        foreground(process.pid)
        child.close()
        while process.poll() is None:
            readable, _, _ = select.select([parent], [], [], 0.2)
            if not readable:
                continue
            packet, _, flags, _ = parent.recvmsg(MAX_MESSAGE + 1)
            if not packet:
                break
            try:
                if flags & socket.MSG_TRUNC:
                    raise AuthenticationError("Loginbericht overschrijdt de maximale lengte.")
                request = decode_request(packet)
                action = request["action"]
                if action in POWER_COMMANDS:
                    completed = subprocess.run(POWER_COMMANDS[action], check=False, timeout=15)
                    power_requested = completed.returncode == 0
                    response = {"result": "power-requested"} if power_requested else {
                        "result": "error", "message": "Het systeem kon de stroomactie niet uitvoeren."
                    }
                else:
                    response = authenticate_request(
                        request, configuration_error="" if mode else error_message,
                    )
                    verified = response["result"] == "authenticated"
                # Password data never reaches command arguments, environment,
                # files or diagnostics. Drop our reference after verification.
                request.clear()
                packet = b""
                parent.send(json.dumps(response).encode("utf-8"))
                if verified or power_requested:
                    break
            except (AuthenticationError, OSError, subprocess.TimeoutExpired) as error:
                message = str(error) if isinstance(error, AuthenticationError) else "Het interne loginverzoek is mislukt."
                parent.send(json.dumps({"result": "error", "message": message}).encode("utf-8"))
        # Successful verification is not enough if the UI/compositor crashes.
        try:
            result = process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            stop_process_group(process)
            result = process.returncode
        return session_authorized(verified, result), power_requested and result == 0
    finally:
        parent.close()
        child.close()
        if process is not None:
            stop_process_group(process)
        foreground(os.getpgrp())


def main() -> int:
    if os.geteuid() != 0:
        print("De loginservice vereist UID 0.", file=sys.stderr)
        return 1
    os.umask(0o077)
    # Keep the supervisor alive while the child owns the controlling terminal.
    # All children have their own process group, preserving real TTY input for
    # the disk installer and permitting complete cleanup before another login.
    signal.signal(signal.SIGTTOU, signal.SIG_IGN)
    RUNTIME.mkdir(mode=0o700, parents=True, exist_ok=True)
    RUNTIME.chmod(0o700)
    error_message = ""
    try:
        settled = subprocess.run(["/usr/bin/udevadm", "settle", "--timeout=10"], check=False, timeout=15)
        if settled.returncode != 0:
            error_message = "USB-initialisatie is nog niet voltooid; de apparatenlijst blijft verversen."
            print(error_message, file=sys.stderr)
    except (OSError, subprocess.SubprocessError) as error:
        print(f"USB-initialisatie: {error}", file=sys.stderr)
        error_message = "De USB-initialisatie meldde een fout. Controleer de actuele apparatenlijst."
    while True:
        try:
            mode = load_mode()
        except AuthenticationError as error:
            mode = None
            error_message = str(error)
        try:
            authorized, power_requested = run_greeter(mode, error_message)
        except (OSError, subprocess.SubprocessError) as error:
            print(f"De grafische login kon niet starten; er is geen sessie geopend: {error}", file=sys.stderr)
            time.sleep(2)
            error_message = "De vorige grafische login is onderbroken. Meld opnieuw aan."
            continue
        if power_requested:
            return 0
        if not authorized or mode not in SESSION_COMMANDS:
            error_message = "De login is gesloten of onderbroken. Meld opnieuw aan."
            time.sleep(1)
            continue
        try:
            process = subprocess.Popen(
                SESSION_COMMANDS[mode], env=base_environment(), process_group=0,
                preexec_fn=claim_terminal if os.isatty(0) else None,
            )
            try:
                foreground(process.pid)
                status = process.wait()
            finally:
                stop_process_group(process)
                foreground(os.getpgrp())
            if status == 78:
                print("De sessie kon niet volledig worden afgesloten. De loginservice is gestopt.", file=sys.stderr)
                return 78
            error_message = "Sessie beëindigd. Meld opnieuw aan." if status == 0 else "De sessie is gestopt met een fout. Meld opnieuw aan."
        except OSError:
            error_message = "De sessie kon niet starten. Meld opnieuw aan."


if __name__ == "__main__":
    raise SystemExit(main())
