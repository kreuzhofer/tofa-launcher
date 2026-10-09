"""Validate and publish checked stable releases and prereleases. No inference credentials are used."""
import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile


def prerelease(version):
    number = r"(?:0|[1-9][0-9]*)"
    if not re.fullmatch(rf"v{number}\.{number}\.{number}-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*", version):
        raise ValueError("Invalid prerelease version: expected vMAJOR.MINOR.PATCH-PRERELEASE")
    if any(part.isdigit() and len(part) > 1 and part.startswith("0")
           for part in version.split("-", 1)[1].split(".")):
        raise ValueError("Invalid prerelease version: numeric identifiers cannot have leading zeros")
    return version


def release_version(version):
    number = r"(?:0|[1-9][0-9]*)"
    if re.fullmatch(rf"v{number}\.{number}\.{number}", version):
        return version
    return prerelease(version)


def gh(*args):
    return subprocess.check_output(["gh", *args], text=True)


def verify_bundle(dist, version):
    expected = {f"tofa_{version}_{system}_{arch}" + (".exe" if system == "windows" else "")
                for system in ("darwin", "linux", "windows") for arch in ("amd64", "arm64")}
    expected.update({"install.sh", "install.ps1", "uninstall.sh", "uninstall.ps1", "LICENSE",
                     "README.md", "THIRD_PARTY_NOTICES.txt", "LICENSE-GO.txt", "PATENTS-GO.txt",
                     "LICENSE-CODEX.txt", "NOTICE-CODEX.txt"})
    if {p.name for p in dist.iterdir()} != expected | {"SHA256SUMS"}:
        raise ValueError("Incomplete or unexpected release assets")
    if any(p.is_symlink() or not p.is_file() for p in dist.iterdir()):
        raise ValueError("Release assets must be regular files")
    seen = set()
    for line in (dist / "SHA256SUMS").read_text().splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match or match[2] not in expected or match[2] in seen:
            raise ValueError("Invalid or duplicate release checksum entry")
        digest, name = match.groups()
        if hashlib.sha256((dist / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Release checksum mismatch: {name}")
        seen.add(name)
    if seen != expected:
        raise ValueError("Missing release checksums")


def publish(dist, version):
    if os.environ.get("GITHUB_EVENT_NAME") != "push" or os.environ.get("GITHUB_REF") != "refs/tags/" + version:
        raise ValueError("Publication requires an explicit release tag push")
    if json.loads(os.environ.get("REQUIRED_RESULTS", "{}")) != {"artifacts": "success", "native": "success"}:
        raise ValueError("Every required job must succeed before publication")
    verify_bundle(dist, version)
    repository = os.environ["GITHUB_REPOSITORY"]
    commit = os.environ["GITHUB_SHA"]
    pages = json.loads(gh("api", f"repos/{repository}/releases", "--paginate", "--slurp"))
    if any(release["tag_name"] == version for page in pages for release in page):
        raise ValueError("Release already exists (including drafts); use a new candidate version")

    def verify_tag():
        remote = json.loads(gh("api", f"repos/{repository}/commits/{version}"))
        if remote["sha"] != commit:
            raise ValueError("Release tag does not match the checked source commit")

    verify_tag()
    is_prerelease = '-' in version
    prerelease_flag = '--prerelease' if is_prerelease else '--prerelease=false'
    channel = 'Experimental prerelease' if is_prerelease else 'Stable release'
    install_base = f'https://github.com/{repository}/releases/' + (f'download/{version}' if is_prerelease else 'latest/download')
    shell_version = f' --version {version}' if is_prerelease else ''
    powershell_version = f' -Version {version}' if is_prerelease else ''
    files = sorted(dist.iterdir())
    with tempfile.TemporaryDirectory(prefix="tofa release ") as temp:
        notes = pathlib.Path(temp) / "notes.md"
        notes.write_text(f"""{channel} `{version}` from commit `{commit}`.

{'Install this pinned prerelease explicitly:' if is_prerelease else 'Install the latest stable release without a version argument:'}

```sh
curl -fsSL {install_base}/install.sh -o install.sh
sh install.sh{shell_version}
```

```powershell
$Installer = Invoke-RestMethod {install_base}/install.ps1 -ErrorAction Stop
& ([scriptblock]::Create($Installer)){powershell_version}
```

All six binaries are cross-built. Native macOS ARM64, Linux amd64 and Windows amd64
checks install and exercise the exact published candidates with synthetic state.
This does not establish real-machine credential-vault or live Codex qualification,
nor native execution on macOS amd64, Linux ARM64 or Windows ARM64. No inference
credential is required by release CI. Signing/notarization is not provided.

`SHA256SUMS` covers every other asset. Retain the bundled licenses and notices.
Changed release files require a new candidate tag; existing assets are not replaced.
""")
        gh("release", "create", version, *(str(path) for path in files), "--repo", repository,
           "--draft", prerelease_flag, "--latest=false", "--verify-tag", "--title", version,
           "--notes-file", str(notes))
        downloaded = pathlib.Path(temp) / "download"
        downloaded.mkdir()
        gh("release", "download", version, "--repo", repository, "--dir", str(downloaded))
        if {p.name: p.read_bytes() for p in downloaded.iterdir()} != {p.name: p.read_bytes() for p in files}:
            raise ValueError("Uploaded release differs from the checked bundle; draft remains private")
        verify_tag()
        gh("release", "edit", version, "--repo", repository, "--draft=false", prerelease_flag,
           "--latest=false" if is_prerelease else "--latest=true", "--verify-tag")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["version", "publish"])
    parser.add_argument("dist", nargs="?", type=pathlib.Path)
    args = parser.parse_args()
    ref = os.environ.get("GITHUB_REF", "")
    version = release_version(ref.removeprefix("refs/tags/")) if ref.startswith("refs/tags/") else "v0.0.0-ci"
    if args.command == "version":
        print(version)
    else:
        if args.dist is None:
            parser.error("publish requires the checked distribution directory")
        publish(args.dist, version)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
