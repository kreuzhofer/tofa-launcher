"""Deterministic, local recovery fixture; deliberately fails without side effects."""
import sys

print('TOFA_RECOVERY_FAILURE_V3: required synthetic dependency unavailable; exit=2', file=sys.stderr)
raise SystemExit(2)
