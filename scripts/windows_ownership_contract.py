"""Negative executable contract for #85; a discovery snapshot NEVER authorizes launch.

Input is a measured OS-boundary inventory, not an ownership token. This prototype
has no production launch/cleanup operations and never adopts an incumbent.
"""
import argparse
import json
import ntpath
from pathlib import Path
import re


def refusal(inventory):
    if (inventory.get('paths_safe') is not True or inventory.get('process_inventory_complete') is not True):
        return 40, 'unsafe_or_incomplete_inventory'
    packages = inventory['packages']
    if len(packages) != 1: return 40, 'package_ambiguous'
    package = packages[0]
    if (package['status'] != 'Ok' or package['architecture'].lower() != 'arm64'
            or not re.fullmatch(r'OpenAI\.Codex_\d+\.\d+\.\d+\.\d+_arm64__[a-z0-9]{13}', package['name'])):
        return 40, 'package_unhealthy'
    root, app = (ntpath.normcase(package[key]) for key in ('root', 'app'))
    if (not ntpath.isabs(root) or ntpath.commonpath([root, app]) != root
            or ntpath.basename(app) != 'chatgpt.exe'):
        return 40, 'package_unhealthy'
    engines = inventory['engines']
    if len(engines) != 1: return 40, 'engine_mismatch'
    engine = engines[0]
    if (engine['architecture'] != 'ARM64' or engine['sha256'] != package['engine_sha256']
            or not re.fullmatch('[0-9a-f]{64}', engine['sha256'])
            or not re.fullmatch(r'[a-z]:\\users\\[^\\]+\\appdata\\local\\openai\\codex\\bin\\[^\\]+\\codex.exe',
                                ntpath.normcase(engine['path']))):
        return 40, 'engine_mismatch'
    # Any observed desktop incumbent makes this bounded contract refuse, even
    # if its executable differs (e.g. another package still running after update).
    if inventory['incumbents']: return 41, 'native_client_busy'
    return 42, 'ownership_unproven'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, required=True)
    options = parser.parse_args()
    try:
        code, reason = refusal(json.loads(options.inventory.read_text(encoding='utf-8-sig')))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        code, reason = 40, 'unsafe_or_incomplete_inventory'
    print(json.dumps({'may_launch': False, 'reason': reason}))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
