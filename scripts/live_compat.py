"""Opt-in prototype qualification through the real launcher and installed Codex.

Uses saved launcher credentials. Runs three scratch coding sessions by default.
The Codex shim observes SSE between the client and the launcher's loopback adapter;
it never receives the Nebius key. Only counts/status/timing leave scratch storage.
Python is a qualification dependency, not a launcher dependency. On Windows,
invoke this harness through qualify_windows.py, which provides its native
observer shim and Job Object supervisor.
"""
import argparse
import hashlib
import hmac
import http.client
import http.server
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import signal
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit

MODEL = "moonshotai/Kimi-K3"
INITIAL = """Use a shell tool to read input.json in this workspace. Create summary.json
with exactly the numeric fields count, total and max calculated from its numbers.
Use a shell tool to validate the result with Python assertions. Do not edit input.json.
Work only in this workspace; do not inspect environment variables or credentials.
Finish with a short explanation of the result. Do not install dependencies."""
FOLLOWUP = """Continue the previous task. Extend summary.json with min and average,
keeping the existing fields. Use a shell tool to verify all five values with Python
assertions against input.json. Work only in this workspace. Finish with a short
explanation. Do not install dependencies or inspect credentials/environment variables."""
EXPECTED = [{"count": 4, "total": 18, "max": 9},
            {"count": 4, "total": 18, "max": 9, "min": -2, "average": 4.5}]


class LoopbackServer(http.server.ThreadingHTTPServer):
    def server_bind(self):
        # HTTPServer performs getfqdn here. A numeric loopback-only listener has
        # no DNS dependency; reverse lookup can stall on native macOS runners.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address


def write_json(path, value):
    with open(path, "x", encoding="utf-8") as stream:
        os.chmod(path, 0o600)
        json.dump(value, stream, indent=2)
        stream.write("\n")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def client_environment(home, codex_home):
    names = ("PATH", "TMPDIR", "LANG", "LC_ALL")
    if os.name == "nt":
        names += ("SystemRoot", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT")
    env = {name: os.environ[name] for name in names if name in os.environ}
    env.update(HOME=str(home), CODEX_HOME=str(codex_home), OTEL_SDK_DISABLED="true")
    if os.name == "nt":
        for name, suffix in (("USERPROFILE", ""), ("LOCALAPPDATA", "local"), ("APPDATA", "roaming"),
                             ("TEMP", "tmp"), ("TMP", "tmp")):
            path = home / suffix
            path.mkdir(parents=True, exist_ok=True)
            env[name] = str(path)
    if os.name == 'nt':
        import windows_sandbox_state
        native = windows_sandbox_state.native_home()
        if native is not None: env['CODEX_HOME'] = str(native)
    return env


def observe(args):
    """Test-only Codex executable shim; forwards only to the supplied local adapter."""
    index = next(i for i, arg in enumerate(args) if arg.startswith("model_providers.nebius-tofa="))
    match = re.search(r'base_url\s*=\s*("[^"]+")', args[index])
    endpoint = json.loads(match.group(1))
    target = urlsplit(endpoint)
    if (target.scheme != "http" or target.hostname != "127.0.0.1" or not target.port
            or target.path or target.query or target.fragment or target.username):
        raise ValueError("expected the launcher's loopback adapter")
    token = os.environ["TOFA_API_KEY"]
    timeout = int(os.environ["TOFA_LIVE_TIMEOUT"])
    if not 1 <= timeout <= 600:
        raise ValueError("invalid observer timeout")
    observations = []
    observation_path = Path(os.environ["TOFA_LIVE_OBSERVATIONS"])
    observation_lock = threading.Lock()

    def persist(index=None, snapshot=None):
        # The parent can terminate the whole client tree at its turn deadline.
        # Atomic snapshots retain usable evidence even if finalization never runs.
        with observation_lock:
            if index is not None:
                observations[index] = snapshot
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                                 dir=observation_path.parent, delete=False) as stream:
                    temporary = Path(stream.name)
                    json.dump(observations, stream)
                    stream.write("\n")
                os.replace(temporary, observation_path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)

    class Observer(http.server.BaseHTTPRequestHandler):
        def log_message(self, *unused):
            pass

        def do_POST(self):
            if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token):
                self.send_error(401)
                return
            if self.path != "/responses":
                self.send_error(404)
                return
            if len(observations) >= 12:
                self.send_error(429)
                return
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 16 * 1024 * 1024:
                self.send_error(413)
                return
            record = {"status": 0, "text_deltas": 0, "tool_deltas": 0,
                      "completed": False, "first_delta_ms": None, "completed_ms": None,
                      "headers_ms": None}
            with observation_lock:
                if len(observations) >= 12:
                    self.send_error(429)
                    return
                index = len(observations)
                observations.append(dict(record))
            # Windows' deadline clock can have a coarse tick on Python 3.12.
            # Stream ordering needs the high-resolution performance counter.
            start = time.perf_counter()

            def checkpoint(stage):
                record.update(stage=stage, elapsed_ms=round((time.perf_counter() - start) * 1000, 3))
                # Handler-local records are never shared with the serializer.
                persist(index, dict(record))

            # The parent enforces the total turn budget across every request and
            # tool round. A socket wait must not impose a shorter hidden limit.
            connection = http.client.HTTPConnection(target.hostname, target.port, timeout=timeout)
            stage = "adapter_request"
            try:
                checkpoint(stage)
                connection.request("POST", "/responses", self.rfile.read(length),
                                   {"Authorization": "Bearer " + token,
                                    "Content-Type": "application/json", "Accept": "text/event-stream"})
                stage = "response_headers"
                checkpoint(stage)
                response = connection.getresponse()
                record["status"] = response.status
                record["headers_ms"] = round((time.perf_counter() - start) * 1000, 3)
                stage = "client_write"
                checkpoint(stage)
                self.send_response(response.status)
                self.send_header("Content-Type", response.getheader("Content-Type", "application/octet-stream"))
                self.end_headers()
                while True:
                    stage = "adapter_read"
                    if record["stage"] != stage:
                        checkpoint(stage)
                    line = response.readline(1024 * 1024)
                    if not line:
                        break
                    stage = "client_write"
                    self.wfile.write(line)
                    self.wfile.flush()
                    if line.startswith(b"data: "):
                        try:
                            event = json.loads(line[6:])
                        except (ValueError, UnicodeDecodeError):
                            continue
                        kind = event.get("type") if isinstance(event, dict) else None
                        if (kind in ("response.output_text.delta", "response.function_call_arguments.delta")
                                and isinstance(event.get("delta"), str) and event["delta"]
                                and not record["completed"]):
                            field = "text_deltas" if kind == "response.output_text.delta" else "tool_deltas"
                            record[field] += 1
                            if record["first_delta_ms"] is None:
                                record["first_delta_ms"] = round((time.perf_counter() - start) * 1000, 3)
                                checkpoint("adapter_read")
                        if kind in ("response.failed", "response.incomplete", "error"):
                            record["failure"] = "response_incomplete"
                        if kind == "response.completed":
                            record["completed"] = True
                            record["completed_ms"] = round((time.perf_counter() - start) * 1000, 3)
                            checkpoint("completed")
            except (OSError, http.client.HTTPException) as error:
                if stage == "client_write" and record["completed"] and isinstance(error, (BrokenPipeError, ConnectionResetError)):
                    record["client_closed_after_completion"] = True
                else:
                    record["transport_error"] = True
                    record["error_stage"] = stage
                    record["error_kind"] = "timeout" if isinstance(error, (socket.timeout, TimeoutError)) else "connection"
            finally:
                connection.close()
                checkpoint("completed" if record["completed"] and not record.get("transport_error") else stage)

    server = LoopbackServer(("127.0.0.1", 0), Observer)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    replacement = json.dumps(f"http://127.0.0.1:{server.server_port}")
    args[index] = args[index][:match.start(1)] + replacement + args[index][match.end(1):]
    # The launcher keeps its normal HOME for credential storage. Only the actual
    # client gets the scratch HOME, configuration and allowlisted environment.
    env = client_environment(Path(os.environ["TOFA_LIVE_HOME"]), Path(os.environ["TOFA_LIVE_CODEX_HOME"]))
    env["TOFA_API_KEY"] = token
    client = json.loads(os.environ["TOFA_LIVE_CODEX"]) if os.name == "nt" else [os.environ["TOFA_LIVE_CODEX"]]
    try:
        if os.name == 'nt':
            import windows_sandbox_state
            args = windows_sandbox_state.client_arguments(args)
        result = subprocess.call(client + args, env=env)
    finally:
        server.shutdown()
        server.server_close()
        persist()
    return result


def stop(process):
    if os.name == "nt":
        import windows_process
        windows_process.stop(process)
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=3)
    except ProcessLookupError:
        pass


def turn(command, env, workspace, prompt, timeout):
    """Consume client output without retaining conversation text or launcher project IDs."""
    summary = {"exit_code": None, "tools_succeeded": 0, "turn_completed": False,
               "client_error": False, "metadata_warning": False, "timed_out": False,
               "reasoning_items": 0, "answer_items": 0, "reasoning_output_tokens": None}
    started = time.perf_counter()
    thread_ids = []
    if os.name == "nt":
        import windows_process
        command = windows_process.supervised(command, env["TOFA_LIVE_SUPERVISOR"])
    process = subprocess.Popen(command, cwd=workspace, env=env, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=os.name != "nt")

    def consume(stream, events):
        size = 0
        for line in iter(lambda: stream.readline(1024 * 1024), b""):
            size += len(line)
            if size > 8 * 1024 * 1024:
                summary["output_limit"] = True
                if os.name == "nt": process.kill()
                else: os.killpg(process.pid, signal.SIGTERM)
                break
            if b"Model metadata for" in line:
                summary["metadata_warning"] = True
            if not events:
                continue
            try:
                event = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(event, dict):
                continue
            kind = event.get("type")
            if kind == "thread.started":
                identity = event.get("thread_id", "")
                if re.fullmatch(r"[a-fA-F0-9-]{36}", identity):
                    thread_ids.append(identity)
            if kind == "turn.completed":
                summary["turn_completed"] = True
                usage = event.get('usage')
                tokens = usage.get('reasoning_output_tokens') if isinstance(usage, dict) else None
                if type(tokens) is int and tokens >= 0:
                    summary['reasoning_output_tokens'] = tokens
            if kind in ("error", "turn.failed"):
                summary["client_error"] = True
            item = event.get("item", {})
            if kind == 'item.completed' and item.get('type') == 'reasoning':
                summary['reasoning_items'] += 1
            if kind == 'item.completed' and item.get('type') == 'agent_message':
                summary['answer_items'] += 1
            if (kind == "item.completed" and item.get("type") == "command_execution"
                    and item.get("status") == "completed" and item.get("exit_code") == 0):
                summary["tools_succeeded"] += 1
                if env.get("TOFA_EVAL_MARKER"):
                    summary["evaluation_marker_executed"] = (
                        summary.get("evaluation_marker_executed", False) or
                        str(item.get("aggregated_output", "")).rstrip("\r\n") == env["TOFA_EVAL_MARKER"])

    readers = [threading.Thread(target=consume, args=(process.stdout, True), daemon=True),
               threading.Thread(target=consume, args=(process.stderr, False), daemon=True)]
    for reader in readers:
        reader.start()
    try:
        process.stdin.write(prompt.encode())
        process.stdin.close()
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        summary["timed_out"] = True
        stop(process)
    except BaseException:
        stop(process)
        raise
    finally:
        for reader in readers:
            reader.join(timeout=4)
        process.stdout.close()
        process.stderr.close()
    summary["exit_code"] = process.returncode
    summary["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
    if os.name == 'nt':
        import windows_sandbox_state
        windows_sandbox_state.record_sessions(thread_ids)
    return summary, thread_ids


def run_one(options, root):
    workspace = root / "workspace"
    workspace.mkdir()
    if os.name == 'nt':
        import windows_sandbox_state
        if windows_sandbox_state.native_home() is not None:
            windows_sandbox_state.prepare_workspace(workspace)
    client_home = root / "codex-home"
    client_home.mkdir()
    scratch_home = root / "home"
    scratch_home.mkdir()
    config = client_home / "config.toml"
    config.write_text('allow_login_shell = false\n\n[projects.' + json.dumps(str(workspace))
                      + ']\ntrust_level = "trusted"\n')
    if os.name == 'nt':
        # A new isolated client home has no selected native sandbox backend.
        mode = 'elevated' if windows_sandbox_state.native_home() is not None else 'unelevated'
        with config.open('a') as stream: stream.write('\n[windows]\nsandbox = ' + json.dumps(mode) + '\n[sandbox_workspace_write]\nexclude_slash_tmp = true\nexclude_tmpdir_env_var = true\n')
    before = digest(config)
    (workspace / "input.json").write_text('{"numbers":[4,-2,7,9]}\n')
    original_input = digest(workspace / "input.json")
    shim = root / "bin"
    shim.mkdir()
    if os.name == "nt":
        import windows_process
        supervisor = getattr(options, "supervisor", None) or windows_process.build_supervisor(root)
        shutil.copyfile(supervisor, shim / "codex.exe")
    else:
        shim_path = shim / "codex"
        shim_path.write_text("#!/bin/sh\nexec " + shlex.quote(sys.executable) + " "
                             + shlex.quote(str(getattr(options, "observer_harness", Path(__file__).resolve()))) + ' --observe "$@"\n')
        shim_path.chmod(0o700)
    env = dict(os.environ)
    env.update(PATH=str(shim) + os.pathsep + os.environ.get("PATH", ""),
               TOFA_LIVE_TIMEOUT=str(options.timeout),
               TOFA_LIVE_HOME=str(scratch_home), TOFA_LIVE_CODEX_HOME=str(client_home),
               TOFA_LIVE_CODEX=json.dumps(options.codex) if os.name == "nt" else options.codex)
    if os.name == "nt":
        env.update(TOFA_LIVE_PYTHON=sys.executable, TOFA_LIVE_HARNESS=str(Path(getattr(options, "observer_harness", Path(__file__).resolve())).resolve()),
                   TOFA_LIVE_SUPERVISOR=str(supervisor))
    base = [options.launcher, "launch", "codex", "--model", getattr(options, "model", MODEL), "--allow-unverified", "--",
            "--ask-for-approval", "never", "--sandbox", "workspace-write", "exec"]
    if getattr(options, "guardian_model", None) is not None:
        base[base.index("--"):base.index("--")] = ["--evaluation-guardian-model", options.guardian_model]
    turns = []
    session = None
    same_session = False
    for number, prompt in enumerate((INITIAL, FOLLOWUP)):
        print(f"  Turn {number + 1}/2", flush=True)
        observation_path = root / f"stream-{number}.json"
        env["TOFA_LIVE_OBSERVATIONS"] = str(observation_path)
        args = (["resume", session] if number else []) + ["--skip-git-repo-check", "--json", "-"]
        try:
            result, identities = turn(base + args, env, workspace, prompt, options.timeout)
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
            # Preserve earlier turns and the current observer's persisted requests.
            result = {"exit_code": None, "tools_succeeded": 0, "turn_completed": False,
                      "client_error": True, "metadata_warning": False, "timed_out": False,
                      "elapsed_ms": None, "harness_defect": True}
            identities = []
        if number == 0:
            session = identities[0] if len(identities) == 1 else None
        else:
            same_session = identities == [session]
        checks = {"summary_status": "unreadable", "unexpected_field_count": None,
                  "expected_fields_match": {key: False for key in EXPECTED[number]},
                  "input_preserved": False}
        summary_matches = False
        try:
            summary = json.loads((workspace / "summary.json").read_text())
            checks["summary_status"] = "object" if isinstance(summary, dict) else "not_object"
            if isinstance(summary, dict):
                checks["expected_fields_match"] = {
                    key: summary.get(key) == value for key, value in EXPECTED[number].items()}
                checks["unexpected_field_count"] = len(summary.keys() - EXPECTED[number].keys())
            # Preserve exact object equality; partial field matches cannot pass.
            summary_matches = summary == EXPECTED[number]
        except FileNotFoundError:
            checks["summary_status"] = "missing"
        except ValueError:
            checks["summary_status"] = "invalid_json"
        except OSError:
            pass
        try:
            checks["input_preserved"] = digest(workspace / "input.json") == original_input
        except OSError:
            pass
        result["file_checks"] = checks
        result["files_correct"] = summary_matches and checks["input_preserved"]
        try:
            streams = json.loads(observation_path.read_text())
        except (OSError, ValueError):
            streams = []
        result["streams"] = streams
        result["streaming_observed"] = any(
            s["status"] == 200 and s["completed"] and s["text_deltas"] >= 2
            and s["first_delta_ms"] < s["completed_ms"] for s in streams)
        result["passed"] = (result["exit_code"] == 0 and result["turn_completed"]
                            and result["tools_succeeded"] > 0 and result["files_correct"]
                            and result["streaming_observed"] and not result["client_error"]
                            and not result["metadata_warning"] and not result["timed_out"]
                            and not result.get("output_limit", False)
                            and all(s["status"] == 200 and s["completed"] and not s.get("transport_error") and not s.get("failure") for s in streams))
        turns.append(result)
        print("  Turn passed" if result["passed"] else "  Turn failed", flush=True)
        if not session or result["exit_code"] != 0:
            break
    try:
        config_preserved = digest(config) == before
    except OSError:
        config_preserved = False
        turns[-1]["harness_defect"] = True
    auth_absent = not (client_home / "auth.json").exists()
    preserved = config_preserved and auth_absent
    return {"turns": turns, "same_session": same_session, "scratch_config_preserved": config_preserved,
            "scratch_auth_absent": auth_absent, "scratch_settings_preserved": preserved,
            "harness_defect": any(t.get("harness_defect") for t in turns),
            "passed": len(turns) == 2 and same_session and preserved and all(t["passed"] for t in turns)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launcher", required=True, help="built tofa executable; reads saved credentials")
    parser.add_argument("--codex", default=shutil.which("codex"))
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=180, help="seconds per turn")
    parser.add_argument("--output", required=True, help="new sanitized JSON evidence file")
    options = parser.parse_args()
    if os.name != "posix" or not 1 <= options.runs <= 10 or not 1 <= options.timeout <= 600:
        parser.error("requires macOS/Linux, 1–10 runs and a 1–600 second turn timeout")
    for name in ("launcher", "codex"):
        value = getattr(options, name)
        if not value or not Path(value).is_file() or not os.access(value, os.X_OK):
            parser.error(f"{name} must be an executable file")
        setattr(options, name, str(Path(value).resolve()))
    output = Path(options.output).resolve()
    if output.exists() or not output.parent.is_dir():
        parser.error("output must be a new file in an existing directory")
    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    launcher_home = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "tofa"
    watched = {"codex_config": codex_home / "config.toml", "codex_auth": codex_home / "auth.json",
               "launcher_config": launcher_home / "config.yml", "launcher_file_credential": launcher_home / "credentials.yml"}
    before = {name: digest(path) for name, path in watched.items()}
    evidence = {"model": MODEL, "route": "adapted with test-only loopback SSE observer",
                "platform": platform.system() + "/" + platform.machine(),
                "os_release": platform.release(),
                "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "launcher_sha256": digest(Path(options.launcher)),
                "harness_sha256": digest(Path(__file__)), "codex_sha256": digest(Path(options.codex)), "runs": []}
    with tempfile.TemporaryDirectory(prefix="tofa-version-") as directory:
        probe_root = Path(directory).resolve()
        (probe_root / "codex").mkdir()
        probe_env = {name: os.environ[name] for name in ("PATH", "TMPDIR", "LANG", "LC_ALL") if name in os.environ}
        probe_env.update(HOME=str(probe_root), CODEX_HOME=str(probe_root / "codex"))
        for name in ("launcher", "codex"):
            result = subprocess.run([getattr(options, name), "--version"], env=probe_env,
                                    capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                raise RuntimeError("version probe failed")
            evidence[name + "_version"] = result.stdout.strip()
    try:
        for number in range(options.runs):
            print(f"Live run {number + 1}/{options.runs}: {MODEL}", flush=True)
            with tempfile.TemporaryDirectory(prefix="tofa-live-") as directory:
                result = run_one(options, Path(directory).resolve())
            evidence["runs"].append(result)
            print("PASS" if result["passed"] else "FAIL", flush=True)
    finally:
        evidence["normal_files_preserved"] = {name: before[name] == digest(path) for name, path in watched.items()}
        evidence["normal_settings_preserved"] = all(evidence["normal_files_preserved"].values())
        evidence["passed"] = (len(evidence["runs"]) == options.runs and evidence["normal_settings_preserved"]
                              and all(run["passed"] for run in evidence["runs"]))
        write_json(output, evidence)
        print("Qualification passed" if evidence["passed"] else "Qualification failed; inspect the sanitized report", flush=True)
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    try:
        sys.exit(observe(sys.argv[2:]) if sys.argv[1:2] == ["--observe"] else main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, StopIteration, KeyError):
        # Exceptions may contain raw argv, paths or provider output. Keep them private.
        print("Live harness failed; see sanitized evidence if available.", file=sys.stderr)
        sys.exit(1)
