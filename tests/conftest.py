"""Test bootstrap helpers.

Ensures the project root is importable when running tests without installing
the package (common for local dev).
"""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
