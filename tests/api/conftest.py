"""Scoped fixtures for the vendored Samsung Art client unit tests."""

import sys
import types
from pathlib import Path

import pytest

API_DIR = (
    Path(__file__).resolve().parents[2]
    / "custom_components"
    / "samsungtv_smart"
    / "api"
)
# Load the vendored API as a package so relative imports such as
# ``from . import _image_prep`` work without importing the full Home Assistant
# integration package (which would make these focused unit tests heavyweight).
API_PACKAGE = "samsungtv_smart_test_api"
package = types.ModuleType(API_PACKAGE)
package.__path__ = [str(API_DIR)]
sys.modules.setdefault(API_PACKAGE, package)
sys.path.insert(0, str(API_DIR))


@pytest.fixture
def art_client():
    """A SamsungTVAsyncArt instance that never opens a real socket."""
    from samsungtv_smart_test_api import art  # noqa: PLC0415

    # Existing focused tests use ``import art`` for constants. Preserve that
    # lightweight alias while loading the module with valid package semantics.
    sys.modules.setdefault("art", art)

    return art.SamsungTVAsyncArt(
        host="192.0.2.10", port=8002, token="tok", name="pytest"
    )
