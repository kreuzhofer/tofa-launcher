import sys, unittest
from pathlib import Path
root = Path.cwd()
sys.path.insert(0, str(root / 'scripts'))
sys.argv = [sys.argv[0], str(root / 'dist/tofa_v0.0.0-prototype_darwin_arm64')]
import terminal_test
import lifecycle_test
lifecycle_test.DIST = root / 'dist'
lifecycle_test.VERSION = 'v0.0.0-prototype'
suite = unittest.defaultTestLoader.discover(str(root / 'scripts'), pattern='*_test.py')
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(not result.wasSuccessful())
