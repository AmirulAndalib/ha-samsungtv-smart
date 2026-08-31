"""Tests for matte_id validation on art_upload (#243)."""

import asyncio
from pathlib import Path
import unittest


def _load_validator():
    """Extract _validate_matte_id and _ids without importing Home Assistant.

    media_player.py pulls in aiohttp and the whole HA stack, which the test
    requirements do not install, so the method is compiled on its own.
    """
    source = (
        Path(__file__).parents[1]
        / "custom_components"
        / "samsungtv_smart"
        / "media_player.py"
    ).read_text()

    start = source.index("    async def _validate_matte_id(")
    end = source.index("    async def async_art_upload(")
    body = source[start:end]

    module_src = "class _Device:\n" + body
    namespace: dict = {}
    exec(compile(module_src, "matte_validator", "exec"), namespace)
    return namespace["_Device"]


_Device = _load_validator()


class _FakeArtApi:
    """Matte lists in the two shapes the TVs are known to return."""

    def __init__(self, types, colors, raises=False):
        self._types = types
        self._colors = colors
        self._raises = raises

    async def get_matte_list(self, include_color: bool = False):
        if self._raises:
            raise RuntimeError("TV unreachable")
        return self._types, self._colors


class _FakeLog:
    def debug(self, *args, **kwargs):
        pass


def _device(types, colors, raises=False):
    device = _Device()
    device._art_api = _FakeArtApi(types, colors, raises)
    device._log = _FakeLog()
    return device


def _validate(device, matte_id):
    return asyncio.run(device._validate_matte_id(matte_id))


TYPES = ["none", "modern", "shadowbox", "flexible"]
COLORS = ["polar", "apricot", "black"]


class MatteValidationTest(unittest.TestCase):
    """A bad matte must be refused before it reaches the TV."""

    def test_valid_matte_passes(self):
        self.assertIsNone(_validate(_device(TYPES, COLORS), "modern_apricot"))

    def test_unknown_colour_is_rejected(self):
        error = _validate(_device(TYPES, COLORS), "modern_chartreuse")
        self.assertIsNotNone(error)
        self.assertIn("chartreuse", error)
        self.assertIn("apricot", error)

    def test_unknown_type_is_rejected(self):
        error = _validate(_device(TYPES, COLORS), "artdeco_polar")
        self.assertIsNotNone(error)
        self.assertIn("artdeco", error)

    def test_both_halves_unknown_are_both_reported(self):
        error = _validate(_device(TYPES, COLORS), "artdeco_chartreuse")
        self.assertIn("artdeco", error)
        self.assertIn("chartreuse", error)

    def test_dict_shaped_lists_are_understood(self):
        device = _device(
            [{"matte_type": "modern"}, {"matte_type": "none"}],
            [{"color": "apricot"}, {"color": "polar"}],
        )
        self.assertIsNone(_validate(device, "modern_apricot"))
        self.assertIsNotNone(_validate(device, "modern_black"))

    def test_none_and_empty_are_always_allowed(self):
        device = _device(TYPES, COLORS)
        self.assertIsNone(_validate(device, "none"))
        self.assertIsNone(_validate(device, ""))
        self.assertIsNone(_validate(device, None))

    def test_unreadable_list_never_blocks_an_upload(self):
        device = _device(TYPES, COLORS, raises=True)
        self.assertIsNone(_validate(device, "anything_at_all"))

    def test_empty_list_never_blocks_an_upload(self):
        self.assertIsNone(_validate(_device([], []), "modern_apricot"))


if __name__ == "__main__":
    unittest.main()
