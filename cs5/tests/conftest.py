"""
Shared test fixtures and path configuration for CS5 tests.

Adds cs5/src to sys.path so test files can import services, agents, etc.
"""

import sys
from pathlib import Path

# Add cs5/src to path so imports work (services.cs3_client, etc.)
_src_dir = str(Path(__file__).resolve().parent.parent / "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)
