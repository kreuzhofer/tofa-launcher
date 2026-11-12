"""Synthetic external executables; no real credentials, inference or GitHub access."""
import http.server
import json
import os
from pathlib import Path
import re
import shutil
import socket
import socketserver
import subprocess
import sys
import threading
import urllib.request
import time
import ctypes
from ctypes import wintypes

role = sys.argv.pop(1).lower()
args = sys.argv[1:]
if role in ("codex.exe", "actual-client.exe"):
    if args == ["--version"]:
        print("codex-cli 0.100.0"); sys.exit()
    assert os.environ["USERPROFILE"] == os.environ["HOME"]
    assert Path(os.environ["LOCALAPPDATA"]).is_relative_to(Path(os.environ["HOME"]))
    assert "FIXTURE_ROOT" not in os.environ
    provider = next(a for a in args if a.startswith("model_providers."))
    endpoint = json.loads(re.search(r'base_url\s*=\s*("[^"]+")', provider)[1])
    request = urllib.request.Request(endpoint + "/responses", data=b"{}", headers={"Authorization": "Bearer " + os.environ["TOFA_API_KEY"]})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=5) as response:
        response.read()
    values = {"count": 4, "total": 18, "max": 9}
    if "resume" in args: values.update(min=-2, average=4.5)
    Path("summary.json").write_text(json.dumps(values))
    print(json.dumps({"type": "thread.started", "thread_id": "11111111-1111-4111-8111-111111111111"}))
    print(json.dumps({"type": "item.completed", "item": {"type": "command_execution", "status": "completed", "exit_code": 0}}))
    print(json.dumps({"type": "turn.completed"}))
    sys.exit()

root = Path(os.environ["FIXTURE_ROOT"])
mode = os.environ["FIXTURE_MODE"]
assets = root / "assets"
if role == "gh.exe":
    if mode == "download_failure": sys.exit(1)
    if args[0] == "api":
        print(json.dumps({"sha": "1234567890abcdef1234567890abcdef12345678"} if "/commits/" in args[1]
                         else {"tag_name": "v0.1.0-rc.1", "draft": False, "prerelease": True}))
    else:
        target = Path(args[args.index("--dir") + 1])
        for source in assets.iterdir(): shutil.copyfile(source, target / source.name)
    sys.exit()

config = root / "local/tofa"
backend = os.environ.get("FIXTURE_BACKEND", "file")
reference = os.environ["FIXTURE_REFERENCE"]
class Credential(ctypes.Structure):
    _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR), ("LastWritten", wintypes.FILETIME),
                ("CredentialBlobSize", wintypes.DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
                ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
                ("Attributes", ctypes.c_void_p), ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]
def vault_write():
    secret = ctypes.create_string_buffer(b"PRIVATE_KEY")
    credential = Credential(Type=1, TargetName="io.nebius.tofa.prototype:" + reference, Persist=2,
                            CredentialBlobSize=11, CredentialBlob=ctypes.cast(secret, ctypes.POINTER(ctypes.c_byte)))
    api = ctypes.WinDLL("advapi32", use_last_error=True)
    assert api.CredWriteW(ctypes.byref(credential), 0)
def vault_delete():
    api = ctypes.WinDLL("advapi32", use_last_error=True)
    api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    assert api.CredDeleteW("io.nebius.tofa.prototype:" + reference, 1, 0) or ctypes.get_last_error() == 1168
def vault_exists():
    api = ctypes.WinDLL("advapi32", use_last_error=True)
    api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)]
    api.CredFree.argtypes = [ctypes.c_void_p]
    pointer = ctypes.c_void_p()
    if not api.CredReadW("io.nebius.tofa.prototype:" + reference, 1, 0, ctypes.byref(pointer)):
        assert ctypes.get_last_error() == 1168
        return False
    try:
        credential = ctypes.cast(pointer, ctypes.POINTER(Credential)).contents
        return ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize) == b"PRIVATE_KEY"
    finally:
        api.CredFree(pointer)
if args == ["__vault_check"]:
    sys.exit(0 if vault_exists() else 1)
if args == ["__vault_cleanup"]:
    vault_delete(); sys.exit()
if args == ["--version"]:
    print("tofa v0.1.0-rc.1"); sys.exit()
if args[:2] == ["auth", "login"]:
    (config / "config.yml").write_text("credential_backend: " + backend + "\n")
    if backend == "keyring":
        vault_write()
        (config / "keyring-refs").mkdir(exist_ok=True)
        (config / "keyring-refs" / reference).write_text("reference")
    else: (config / "credentials.yml").write_text("PRIVATE_KEY")
    with (root / "logins").open("a") as out: out.write("login\n")
    sys.exit()
if args == ["doctor"]:
    print("Credential backend: " + backend + " (access not tested)"); sys.exit()
if args[0] == "uninstall":
    helper = Path(os.environ["TEMP"]) / "tofa-uninstall-fixture.ps1"
    source = (assets / "uninstall.ps1").read_text()
    if mode == "lost_login": (config / "credentials.yml").unlink()
    if mode == "lost_vault": vault_delete()
    if mode == "helper_failure": source = "throw 'PRIVATE_HELPER_FAILURE'\n"
    if mode == "helper_cancel": source = "exit 77\n"
    if mode == "helper_timeout":
        delay = "$PID | Set-Content -LiteralPath '" + str(root / "helper.pid").replace("'", "''") + "'\nStart-Sleep -Seconds 60\n"
        source = source.replace("$ErrorActionPreference='Stop'", "$ErrorActionPreference='Stop'\n" + delay, 1)
    source += "\nRemove-Item -LiteralPath $PSCommandPath\n"
    if mode == "helper_completed_failure": source += "exit 77\n"
    helper.write_text(source)
    command = ["powershell.exe", "-NoProfile", "-File", str(helper), "-WaitPid", str(os.getppid())]
    if "--purge" in args: command += ["-Purge"]
    subprocess.Popen(command)
    print("Uninstaller started; it will report completion after tofa exits.")
    sys.exit()
assert vault_exists() if backend == "keyring" else (config / "credentials.yml").read_text() == "PRIVATE_KEY"
if mode == "preservation_failure": (root / ".codex/auth.json").write_text("changed")
if mode == "default_neighbor_changed": (config / "install/unrelated.txt").write_text("changed")
if mode == "live_timeout":
    (root / "live-started").touch()
    time.sleep(60)
def no_dns(*args): raise RuntimeError("numeric loopback must not resolve DNS")
socket.getfqdn = no_dns
class Adapter(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        self.send_response(200); self.end_headers()
        for kind in ("response.output_text.delta", "response.output_text.delta", "response.completed"):
            self.wfile.write(("data: " + json.dumps({"type": kind, "delta": "PRIVATE_CONVERSATION"}) + "\n\n").encode())
            self.wfile.flush()
class Loopback(http.server.ThreadingHTTPServer):
    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address
server = Loopback(("127.0.0.1", 0), Adapter)
threading.Thread(target=server.serve_forever, daemon=True).start()
os.environ["TOFA_API_KEY"] = "PRIVATE_LOCAL_TOKEN"
provider = "model_providers.nebius-tofa={base_url=" + json.dumps("http://127.0.0.1:" + str(server.server_port)) + "}"
code = subprocess.call(["codex.exe", "-c", provider] + args[args.index("--") + 1:])
server.shutdown(); server.server_close()
if mode in ("saved_config_changed", "saved_credential_changed"):
    counter = root / (mode + '.count')
    count = int(counter.read_text()) + 1 if counter.exists() else 1
    counter.write_text(str(count))
    if count == 4:
        if mode == "saved_config_changed": (config / "config.yml").write_text("changed after live")
        else: (config / "credentials.yml").write_text("CHANGED_KEY")
sys.exit(code)
