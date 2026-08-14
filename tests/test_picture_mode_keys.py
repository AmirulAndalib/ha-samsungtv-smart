"""Tests for the picture mode -> remote key resolution."""

import importlib.util
import unittest
from pathlib import Path

# Loaded straight from its file: the module depends only on the standard
# library, and importing it through the package would drag in aiohttp and the
# whole Home Assistant integration just to test a pure function.
_MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "samsungtv_smart"
    / "picture_mode_keys.py"
)
_spec = importlib.util.spec_from_file_location("picture_mode_keys", _MODULE_PATH)
_pmk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pmk)

KEY_DYNAMIC = _pmk.KEY_DYNAMIC
KEY_ECO = _pmk.KEY_ECO
KEY_MOVIE = _pmk.KEY_MOVIE
KEY_STANDARD = _pmk.KEY_STANDARD
picture_mode_ws_key = _pmk.picture_mode_ws_key


class TestModeId(unittest.TestCase):
    """The internal id wins whenever the TV exposes one."""

    def test_ids_resolve(self):
        for mode_id, expected in (
            ("modeDynamic", KEY_DYNAMIC),
            ("modeStandard", KEY_STANDARD),
            ("modeMovie", KEY_MOVIE),
            ("modeEco", KEY_ECO),
        ):
            with self.subTest(mode_id=mode_id):
                self.assertEqual(picture_mode_ws_key("whatever", mode_id), expected)

    def test_unknown_id_falls_through_to_the_name(self):
        # modeNatural has no key; the name must still be consulted rather than
        # the whole lookup giving up.
        self.assertEqual(
            picture_mode_ws_key("Dynamisk", "modeNatural"),
            KEY_DYNAMIC,
        )


class TestLocalisedNames(unittest.TestCase):
    """Real mode lists taken from the issues, where no id map was available."""

    def test_norwegian_206(self):
        self.assertEqual(picture_mode_ws_key("Dynamisk"), KEY_DYNAMIC)
        self.assertEqual(picture_mode_ws_key("Standard"), KEY_STANDARD)

    def test_slovak_197(self):
        self.assertEqual(picture_mode_ws_key("Dynamický"), KEY_DYNAMIC)
        self.assertEqual(picture_mode_ws_key("Štandardný"), KEY_STANDARD)
        self.assertEqual(picture_mode_ws_key("Film"), KEY_MOVIE)
        # Prirodzený (Natural) deliberately has no key.
        self.assertIsNone(picture_mode_ws_key("Prirodzený"))

    def test_other_locales(self):
        cases = {
            KEY_DYNAMIC: [
                "Dynamic",
                "Dynamique",
                "Dynamisch",
                "Dinamico",
                "Dinâmico",
                "Dinamik",
                "Dynamiczny",
                "Dinamikus",
            ],
            KEY_STANDARD: [
                "Standard",
                "Estándar",
                "Standaard",
                "Standardowy",
                "Štandardný",
                "Standart",
                "Normál",
                "Vakio",
            ],
            KEY_MOVIE: ["Movie", "Film", "Cinéma", "Película", "Elokuva"],
            KEY_ECO: ["Eco", "Éco", "Öko", "Eko"],
        }
        for expected, names in cases.items():
            for name in names:
                with self.subTest(name=name):
                    self.assertEqual(picture_mode_ws_key(name), expected)


class TestRefusals(unittest.TestCase):
    """Sending the wrong mode is worse than sending none."""

    def test_filmmaker_never_maps_to_movie(self):
        # "FILMMAKER MODE" contains "film" and must be rejected first.
        for name in ("FILMMAKER MODE", "Filmmaker Mode", "filmmaker"):
            with self.subTest(name=name):
                self.assertIsNone(picture_mode_ws_key(name))

    def test_unknown_names(self):
        for name in ("", "   ", "Ambient", "Game", "Sports", "HDR+"):
            with self.subTest(name=name):
                self.assertIsNone(picture_mode_ws_key(name))

    def test_natural_english_only(self):
        # Legacy behaviour kept verbatim for the English word...
        self.assertEqual(picture_mode_ws_key("Natural"), KEY_MOVIE)
        # ...and deliberately not generalised to other languages.
        for name in ("Naturlig", "Naturel", "Natürlich", "Naturale", "Přirozený"):
            with self.subTest(name=name):
                self.assertIsNone(picture_mode_ws_key(name))


class TestRobustness(unittest.TestCase):
    """Inputs that must not raise."""

    def test_padding_and_case(self):
        # Samsung pads localized names in some locales (#197).
        self.assertEqual(picture_mode_ws_key("  Dynamisk  "), KEY_DYNAMIC)
        self.assertEqual(picture_mode_ws_key("DYNAMIC"), KEY_DYNAMIC)

    def test_empty_inputs(self):
        self.assertIsNone(picture_mode_ws_key("", ""))
        self.assertIsNone(picture_mode_ws_key(" "))


if __name__ == "__main__":
    unittest.main()
