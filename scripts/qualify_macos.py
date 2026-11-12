"""Qualify a pinned prerelease in the current macOS account, with human gates.

Requires Python 3.9+, authenticated gh, curl and installed Codex. Reports stay local.
Linux supports file storage for offline portability; macOS is the qualification target.
"""
import argparse
import json
import os
from pathlib import Path
import platform
import re
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

import live_compat
from release import prerelease

REPOSITORY = "kreuzhofer/tofa-launcher"
CONFIG_OWNED = frozenset({"config.yml", "credentials.yml", ".auth-lock"})
INSTALL_OWNED = frozenset({"bin/tofa", ".path-files", ".tofa-install"})
STAGES = ("preflight", "recovery", "download", "install", "login", "fresh_terminal",
          "live", "uninstall", "reinstall", "saved_login_reuse", "purge")


class Failure(Exception):
    """Only fixed, non-sensitive reason codes may reach reports."""


def command(args, timeout, env=None, interactive=False, accepted=(0,)):
    process = subprocess.Popen(args, env=env, start_new_session=True,
                               stdin=None if interactive else subprocess.DEVNULL,
                               stdout=None if interactive else subprocess.PIPE,
                               stderr=None if interactive else subprocess.PIPE)
    try:
        stdout, _ = process.communicate(timeout=timeout)
    except BaseException:
        live_compat.stop(process)
        raise
    if process.returncode not in accepted:
        raise Failure("command_failed")
    if stdout and len(stdout) > 1024 * 1024:
        raise Failure("output_limit")
    return process.returncode, (stdout or b"").decode("utf-8", errors="strict").strip()


def confirm(message, answer, timeout):
    print(message + f"\nType {answer} to continue: ", end="", flush=True)
    # Read the descriptor one byte at a time: do not buffer the following login's
    # terminal input or a later human gate. Every prompt has a deadline.
    deadline = time.monotonic() + timeout
    response = bytearray()
    while len(response) < 128:
        left = deadline - time.monotonic()
        if left <= 0 or not select.select([sys.stdin], [], [], left)[0]:
            raise Failure("human_confirmation_timeout")
        char = os.read(sys.stdin.fileno(), 1)
        if char in (b"", b"\n"):
            break
        response.extend(char)
    if response.decode("utf-8", errors="replace").strip() != answer:
        raise Failure("human_confirmation_declined")


def file_state(path):
    if path.is_symlink():
        return ("symlink", os.readlink(path), live_compat.digest(path))
    return ("file", live_compat.digest(path)) if path.is_file() else ("absent", None)


def unrelated_state(root, excluded):
    if not root.exists():
        return {}
    return {str(path.relative_to(root)): file_state(path) for path in root.rglob("*")
            if (path.is_file() or path.is_symlink()) and str(path.relative_to(root)) not in excluded
            and "keyring-refs" not in path.relative_to(root).parts}


def startup_files(home, install):
    paths = {home / ".zshrc", Path(os.environ.get("ZDOTDIR", str(home))) / ".zshrc",
             home / ".bashrc", home / ".bash_profile", home / ".bash_login", home / ".profile",
             Path(os.environ.get("XDG_CONFIG_HOME", str(home / ".config"))) / "fish/conf.d/tofa.fish"}
    manifest = install / ".path-files"
    if manifest.is_file():
        paths.update(Path(line) for line in manifest.read_text().splitlines())
    return paths


def shell_content(path):
    if not path.exists():
        return b""
    content = path.read_bytes()
    # The installer adds exactly one leading newline before each owned block.
    return re.sub(rb"\n?# >>> tofa >>>\n.*?# <<< tofa <<<\n", b"", content, flags=re.S).rstrip(b"\n")


def vault_refs(config):
    directory = config / "keyring-refs"
    refs = set()
    if directory.exists():
        for path in directory.iterdir():
            if not re.fullmatch(r"[0-9a-f]{32}", path.name) or not path.is_file() or path.is_symlink():
                raise Failure("invalid_credential_recovery_state")
            refs.add(path.name)
    return refs


def vault_absent(refs, timeout):
    if not refs:
        return True
    if platform.system() != "Darwin":
        raise Failure("native_vault_verification_requires_macos")
    absent = True
    for ref in refs:
        code, _ = command(["security", "find-generic-password", "-s", "io.nebius.tofa.prototype", "-a", ref],
                          timeout, accepted=(0, 44))
        absent = absent and code == 44
    return absent


def download(version, directory, timeout, evidence, assets=None):
    if assets:
        metadata = json.loads((assets / 'release.json').read_text())
    else:
        _, raw = command(["gh", "api", f"repos/{REPOSITORY}/releases/tags/{version}"], timeout)
        metadata = json.loads(raw)
    if metadata.get("tag_name") != version or metadata.get("draft") is not False or metadata.get("prerelease") is not True:
        raise Failure("not_a_published_prerelease")
    if assets:
        raw = (assets / 'commit.json').read_text()
    else:
        _, raw = command(["gh", "api", f"repos/{REPOSITORY}/commits/{version}"], timeout)
    commit = json.loads(raw).get("sha", "")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise Failure("invalid_candidate_commit")
    evidence["candidate"]["commit"] = commit
    system = platform.system().lower()
    arch = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "amd64"}.get(platform.machine())
    if system not in ("darwin", "linux") or not arch:
        raise Failure("unsupported_platform")
    asset = f"tofa_{version}_{system}_{arch}"
    names = (asset, "install.sh", "uninstall.sh")
    args = ["gh", "release", "download", version, "--repo", REPOSITORY, "--dir", str(directory)]
    for name in (*names, "SHA256SUMS"):
        args.extend(["--pattern", name])
    if assets:
        for name in (*names, 'SHA256SUMS'):
            source = assets / name
            if source.is_symlink() or not source.is_file(): raise Failure('invalid_downloaded_asset')
            shutil.copyfile(source, directory / name)
    else:
        command(args, timeout)
    evidence['candidate']['download_boundary'] = 'host-downloaded transfer' if assets else 'authenticated gh'
    checksums = {}
    for line in (directory / "SHA256SUMS").read_text().splitlines():
        match = re.fullmatch(r"([0-9a-fA-F]{64})  (\S+)", line)
        if not match or match[2] in checksums:
            raise Failure("invalid_checksums")
        checksums[match[2]] = match[1].lower()
    for name in names:
        path = directory / name
        if path.is_symlink() or not path.is_file() or live_compat.digest(path) != checksums.get(name):
            raise Failure("checksum_mismatch")
    evidence["candidate"].update(binary_sha256=checksums[asset],
                                  scripts_sha256={name: checksums[name] for name in names[1:]})
    return asset


def save_report(reports, evidence):
    json_report, summary = reports
    json.dump(evidence, json_report, indent=2)
    json_report.write("\n")
    json_report.flush()
    lines = ["# Local prerelease qualification", "", f"Outcome: **{evidence['outcome']}**",
             f"Candidate: `{evidence['candidate']['tag']}`", f"Commit: `{evidence['candidate'].get('commit', 'unknown')}`",
             f"Binary SHA256: `{evidence['candidate'].get('binary_sha256', 'unknown')}`",
             f"Host: {evidence['host']['os']} / {evidence['host']['arch']} / {evidence['host']['release']}",
             f"Codex: {evidence['client'].get('version', 'unknown')}", f"Backend: {evidence['backend']}", "",
             "| Stage | Outcome |", "| --- | --- |"]
    lines.extend(f"| {stage['name']} | {stage['status']} |" for stage in evidence["stages"])
    if "qualification_scope" in evidence:
        lines.extend(["", "Scope: `" + evidence["qualification_scope"] + "`"])
        if evidence["qualification_scope"] == "preserve_lifecycle":
            lines.append("Destructive purge was not run; removed-state fields do not establish a purge result.")
    if "retained_state" in evidence:
        lines.extend(["", "Retained state:"])
        lines.extend(f"- {name}: {value}" for name, value in evidence["retained_state"].items())
    for group in ("preservation", "cleanup"):
        lines.extend(["", group.capitalize() + ":"])
        lines.extend(f"- {name}: {value}" for name, value in evidence[group].items())
    if "reason" in evidence:
        lines.extend(["", "Reason: " + evidence["reason"]])
    lines.extend(["", "No upload was performed. Attach both local reports to the validation issue.",
                  "If incomplete, inspect the cleanup fields and recover the remaining installation/state before rerunning."])
    summary.write("\n".join(lines) + "\n")
    summary.flush()


def prepare_agent_state(options, parser):
    """Explicit operator authorization applies only to a newly owned state tree."""
    if not options.agent_state_root:
        return
    root = options.agent_state_root.absolute()
    if root.exists() or root.is_symlink() or not root.parent.is_dir():
        parser.error("agent state root must be new, in an existing directory")
    root.mkdir(mode=0o700)
    for name in ('config', 'local', 'shell'):
        (root / name).mkdir(mode=0o700)
    options.agent_state_root = root
    # Native vaults need the real HOME. Only owned launcher and shell state move.
    os.environ.update(XDG_CONFIG_HOME=str(root / 'config'), LOCALAPPDATA=str(root / 'local'),
                      TOFA_INSTALL_DIR=str(root / 'install'), ZDOTDIR=str(root / 'shell'))
    if os.name != 'nt':
        os.environ['SHELL'] = '/bin/zsh'


def onboarding_command(binary, options):
    args = [str(binary), '--model', options.model, '--allow-unverified']
    if options.guardian_model:
        args += ['--evaluation-guardian-model', options.guardian_model]
    return args + ['--', '--version']


def qualify(options, reports):
    home = Path.home()
    config = Path(os.environ.get("XDG_CONFIG_HOME", str(home / ".config"))) / "tofa"
    install = Path(os.environ.get("TOFA_INSTALL_DIR", str(home / ".local/share/tofa")))
    binary = install / "bin/tofa"
    codex_home = Path(os.environ.get("CODEX_HOME", str(home / ".codex")))
    watched = {"codex_config": codex_home / "config.toml", "codex_auth": codex_home / "auth.json"}
    before, config_before, install_before, shell_before = {}, {}, {}, {}
    shells = set()
    snapshots_ready = False
    refs = set()
    evidence = {"schema_version": 1, "candidate": {"tag": options.version},
                "host": {"os": platform.system(), "arch": platform.machine(), "release": platform.mac_ver()[0] or platform.release()},
                "operator": "agent" if options.agent_state_root else "human",
                "client": {}, "backend": "unknown", "model": options.model, "guardian_model": options.guardian_model,
                "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "stages": [{"name": name, "status": "pending"} for name in STAGES],
                "preservation": {name: None for name in ("baseline_recorded", "codex_config", "codex_auth",
                                                         "unrelated_config", "unrelated_installation", "shell_settings")},
                "cleanup": {name: None for name in ("scratch_removed", "binary_removed", "ownership_removed",
                                                    "path_entries_removed", "configuration_removed",
                                                    "file_credentials_removed", "vault_credentials_removed")},
                "outcome": "incomplete"}
    active = None
    scratch = None

    def stage(name, action):
        nonlocal active
        active = next(item for item in evidence["stages"] if item["name"] == name)
        active["status"] = "running"
        print("Stage: " + name, flush=True)
        result = action()
        active["status"] = "passed"
        return result

    def preflight():
        nonlocal refs, before, config_before, install_before, shells, shell_before, snapshots_ready
        before = {name: file_state(path) for name, path in watched.items()}
        config_before = unrelated_state(config, CONFIG_OWNED)
        install_before = unrelated_state(install, INSTALL_OWNED)
        shells = startup_files(home, install)
        shell_before = {path: shell_content(path) for path in shells}
        snapshots_ready = True
        if os.name != "posix" or platform.system() not in ("Darwin", "Linux"):
            raise Failure("unsupported_platform")
        for program in (("gh",) if not options.downloaded_assets else ()) + ("curl", "sh", options.codex):
            if not program or not shutil.which(program):
                raise Failure("missing_prerequisite")
        if config.is_symlink() or install.is_symlink() or (config / ".auth-lock").exists():
            raise Failure("unsafe_or_busy_existing_state")
        refs = vault_refs(config)
        evidence["existing_state"] = {"installation": install.exists(), "configuration": (config / "config.yml").exists(),
                                      "file_credentials": (config / "credentials.yml").exists(), "vault_references": bool(refs)}
        probe = Path(scratch.name) / "probe"
        probe.mkdir()
        env = dict(os.environ, HOME=str(probe), CODEX_HOME=str(probe / "codex"))
        _, version = command([options.codex, "--version"], options.timeout, env=env)
        if not re.fullmatch(r"codex-cli [0-9]+(?:\.[0-9]+)+(?:[-+][0-9A-Za-z.-]+)?", version):
            raise Failure("unrecognized_client_version")
        evidence["client"]["version"] = version

    def install_candidate():
        command(["sh", str(downloads / "install.sh"), "--version", options.version], options.timeout,
                env=dict(os.environ, TOFA_RELEASE_BASE_URL=downloads.as_uri()))
        if live_compat.digest(binary) != evidence["candidate"]["binary_sha256"]:
            raise Failure("installed_checksum_mismatch")
        _, version = command([str(binary), "--version"], options.timeout)
        if version != "tofa " + options.version:
            raise Failure("installed_version_mismatch")

    def login():
        nonlocal refs
        print("Enter the real Token Factory credentials in the launcher's interactive prompt. OS prompts may appear.", flush=True)
        args = onboarding_command(binary, options) if options.agent_state_root else [str(binary), "auth", "login"]
        if options.storage and not options.agent_state_root:
            args += ["--storage", options.storage]
        command(args, options.human_timeout, interactive=True)
        _, doctor = command([str(binary), "doctor"], options.timeout)
        match = re.search(r"^Credential backend: (file|keyring) \(", doctor, flags=re.M)
        if not match:
            raise Failure("credential_backend_unknown")
        evidence["backend"] = match[1]
        refs |= vault_refs(config)
        if evidence["backend"] == "keyring" and (not refs or vault_absent(refs, options.timeout)):
            raise Failure("saved_vault_credential_missing")

    def live(name):
        with tempfile.TemporaryDirectory(prefix="live-", dir=scratch.name) as directory:
            settings = SimpleNamespace(launcher=str(binary), codex=options.codex, timeout=options.timeout, model=options.model, guardian_model=options.guardian_model)
            if options.check_pair:
                import qualification_pair
                result = qualification_pair.run(settings, Path(directory).resolve())
            else:
                result = live_compat.run_one(settings, Path(directory).resolve())
        evidence[name] = result
        if any(before[name] != file_state(path) for name, path in watched.items()):
            raise Failure("preservation_failed")
        if not result["passed"]:
            raise Failure("live_assertions_failed")

    def owned_path_blocks_remain():
        paths = shells
        if options.agent_state_root:
            paths = {path for path in shells if path.resolve().is_relative_to(options.agent_state_root.resolve())}
        return any(b"# >>> tofa >>>" in path.read_bytes() for path in paths if path.is_file())

    def uninstall():
        saved = {name: file_state(config / name) for name in ("config.yml", "credentials.yml")}
        saved_refs = vault_refs(config)
        command([str(binary), "uninstall"], options.timeout)
        if binary.exists() or owned_path_blocks_remain():
            raise Failure("uninstall_cleanup_incomplete")
        if saved != {name: file_state(config / name) for name in saved} or saved_refs != vault_refs(config):
            raise Failure("saved_state_changed")

    def purge():
        if not options.agent_state_root: confirm("The live checks passed. Purge removes local tofa preferences and credentials; it does not revoke remote tokens. Confirm your recovery is ready.", "PURGE", options.human_timeout)
        command([str(binary), "uninstall", "--purge"], options.timeout)
        if not vault_absent(refs, options.timeout):
            raise Failure("vault_cleanup_incomplete")

    try:
        scratch = tempfile.TemporaryDirectory(prefix="tofa-qualification-")
        downloads = Path(scratch.name).resolve() / "download"
        downloads.mkdir()
        stage("preflight", preflight)
        stage("recovery", lambda: None if options.agent_state_root else confirm("This run replaces the installed launcher and login, then uninstalls and explicitly purges local tofa state. Existing state: " + json.dumps(evidence["existing_state"]) + ". Prepare any credential backup/recovery or token reissue yourself before continuing. Close other launcher/Codex sessions.", "READY", options.human_timeout))
        stage("download", lambda: download(options.version, downloads, options.timeout, evidence, options.downloaded_assets))
        stage("install", install_candidate)
        if options.agent_state_root: install_candidate()
        shells |= startup_files(home, install)
        stage("login", login)
        def fresh_terminal():
            if not options.agent_state_root:
                return confirm("Open a NEW terminal, verify tofa location/version, and record OS prompts.", "FOUND", options.human_timeout)
            _, output = command(['/bin/zsh', '-ic', 'command -v tofa; tofa --version'], options.timeout)
            if output.splitlines() != [str(binary), 'tofa ' + options.version]:
                raise Failure('fresh_terminal_discovery_failed')
        stage("fresh_terminal", fresh_terminal)
        stage("live", lambda: live("live"))
        stage("uninstall", uninstall)
        stage("reinstall", install_candidate)
        stage("saved_login_reuse", lambda: live("saved_login_reuse"))
        stage("purge", purge)
        evidence["outcome"] = "passed"
    except (KeyboardInterrupt, EOFError):
        evidence["reason"] = "interrupted"
    except Failure as error:
        evidence["outcome"] = "incomplete" if str(error).startswith("human_confirmation") else "failed"
        evidence["reason"] = str(error)
    except subprocess.TimeoutExpired:
        evidence.update(outcome="failed", reason="process_timeout")
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        evidence.update(outcome="failed", reason="operation_failed")
    finally:
        if active and active["status"] == "running":
            active["status"] = evidence["outcome"]
        try:
            if scratch:
                scratch.cleanup()
            evidence["cleanup"]["scratch_removed"] = True
            evidence["cleanup"]["binary_removed"] = not binary.exists()
            evidence["cleanup"]["ownership_removed"] = not (install / ".tofa-install").exists()
            evidence["cleanup"]["path_entries_removed"] = not (install / ".path-files").exists() and not owned_path_blocks_remain()
            evidence["cleanup"]["configuration_removed"] = not (config / "config.yml").exists()
            evidence["cleanup"]["file_credentials_removed"] = not (config / "credentials.yml").exists()
            evidence["cleanup"]["vault_credentials_removed"] = vault_absent(refs, options.timeout) and not vault_refs(config)
            evidence["preservation"]["baseline_recorded"] = snapshots_ready
            evidence["preservation"].update({name: before.get(name) == file_state(path) for name, path in watched.items()})
            evidence["preservation"]["unrelated_config"] = config_before == unrelated_state(config, CONFIG_OWNED)
            evidence["preservation"]["unrelated_installation"] = install_before == unrelated_state(install, INSTALL_OWNED)
            evidence["preservation"]["shell_settings"] = all(shell_content(path) == content for path, content in shell_before.items())
            if evidence["outcome"] == "passed" and not all(evidence["cleanup"].values()):
                evidence.update(outcome="failed", reason="cleanup_incomplete")
            if not all(evidence["preservation"].values()):
                evidence.update(outcome="failed", reason="preservation_failed")
        except (OSError, ValueError, Failure, subprocess.SubprocessError):
            evidence.update(outcome="failed", reason="final_checks_failed")
        try:
            save_report(reports, evidence)
        except OSError:
            print("Could not finish local reports; inspect remaining account state before rerunning.", file=sys.stderr)
            evidence["outcome"] = "failed"
        else:
            print("Qualification " + evidence["outcome"] + ". Local JSON and Markdown reports saved; no upload performed.", flush=True)
    return 0 if evidence["outcome"] == "passed" else 1


def interrupted(*unused):
    raise KeyboardInterrupt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, type=prerelease)
    parser.add_argument("--output", required=True, type=Path, help="new .json file; a matching .md summary is also created")
    parser.add_argument("--downloaded-assets", type=Path, help="trusted host-downloaded release assets plus release.json and commit.json; checksums are reverified locally")
    parser.add_argument("--agent-state-root", type=Path, help="authorize automated lifecycle/purge only in this NEW disposable directory; login remains interactive")
    parser.add_argument("--codex", default=shutil.which("codex"))
    parser.add_argument("--check-pair", action="store_true", help="bounded coding plus native Guardian allow/deny checks; requires --guardian-model")
    parser.add_argument("--model", default=live_compat.MODEL, help="exact main model; remains Experimental")
    parser.add_argument("--guardian-model", help="exact Guardian model; no implicit substitution")
    parser.add_argument("--storage", choices=("file", "keyring"), help="explicit override; normally respect the launcher's selection")
    parser.add_argument("--timeout", type=int, default=180, help="seconds per command or live turn (1–600)")
    parser.add_argument("--human-timeout", type=int, default=900, help="seconds per human step (1–3600)")
    options = parser.parse_args()
    if options.agent_state_root and options.storage:
        parser.error("agent onboarding uses the native vault-first selection; --storage requires the manual login mode")
    if options.check_pair and not options.guardian_model:
        parser.error("--check-pair requires --guardian-model")
    for identity in (options.model, options.guardian_model):
        if identity is not None and not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}/[A-Za-z0-9_.-]{1,128}", identity):
            parser.error("invalid model identity")
    options.output = options.output.resolve()
    if options.output.suffix != ".json" or not options.output.parent.is_dir() or any(
            path.exists() for path in (options.output, options.output.with_suffix(".md"))):
        parser.error("output requires new .json and .md files in an existing directory")
    if not 1 <= options.timeout <= 600 or not 1 <= options.human_timeout <= 3600:
        parser.error("invalid timeout")
    if options.codex:
        options.codex = shutil.which(options.codex) or options.codex
    # Reserve both destinations before touching account state. Keep descriptors
    # open so a path replacement cannot redirect the final evidence writes.
    reports = []
    reserved = []
    try:
        for path in (options.output, options.output.with_suffix(".md")):
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            reserved.append(path)
            reports.append(os.fdopen(descriptor, "w", encoding="utf-8"))
    except OSError:
        for stream in reports:
            stream.close()
        for path in reserved:
            path.unlink()
        parser.error("cannot create the local report files; account state was not changed")
    prepare_agent_state(options, parser)
    signal.signal(signal.SIGTERM, interrupted)
    with reports[0], reports[1]:
        return qualify(options, reports)


if __name__ == "__main__":
    sys.exit(main())
