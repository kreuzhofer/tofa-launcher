#!/bin/bash
# Offline process inventory: only app paths within this test's temporary tree.
# Keep this executable usable under the file-size-limit test.
set -euo pipefail
fixture_root=${HOME%/*}
if [ -n "${FIXTURE_DESKTOP_BUNDLE:-}" ]; then
  fixture_parent=${FIXTURE_DESKTOP_BUNDLE%/*}
  fixture_root=${fixture_parent%/*}
fi
case ${fixture_root##*/} in
  Test*) ;;
  *) echo 'desktop process fixture requires a test temporary tree' >&2; exit 1 ;;
esac
export TOFA_TEST_PROCESS_ROOT="$fixture_root/"
/bin/ps "$@" | /usr/bin/awk 'index($0, ENVIRON["TOFA_TEST_PROCESS_ROOT"]) {print}'
