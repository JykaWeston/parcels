"""Expose the project root (for `custom_components` imports) to pytest."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
