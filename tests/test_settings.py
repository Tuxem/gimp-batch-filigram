# -*- coding: utf-8 -*-
"""Tests unitaires du modèle de préférences (:mod:`lib.settings`).

Couvre la sérialisation/désérialisation, la tolérance aux données corrompues
et la persistance sur disque.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from lib.constants import ExportFormat, NamingMode, Position, SizeMode, WatermarkType
from lib.settings import Settings, SettingsManager


class TestSettingsSerialization(unittest.TestCase):
    def test_roundtrip_preserves_enums(self):
        original = Settings()
        original.watermark_type = WatermarkType.TEXT
        original.position = Position.TOP_LEFT
        original.size_mode = SizeMode.FIXED
        original.naming_mode = NamingMode.DATE
        original.export_format = ExportFormat.WEBP
        original.opacity = 42.5
        original.suffix = "_test"

        restored = Settings.from_dict(original.to_dict())

        self.assertEqual(restored.watermark_type, WatermarkType.TEXT)
        self.assertEqual(restored.position, Position.TOP_LEFT)
        self.assertEqual(restored.size_mode, SizeMode.FIXED)
        self.assertEqual(restored.naming_mode, NamingMode.DATE)
        self.assertEqual(restored.export_format, ExportFormat.WEBP)
        self.assertEqual(restored.opacity, 42.5)
        self.assertEqual(restored.suffix, "_test")

    def test_to_dict_is_json_serializable(self):
        # Ne doit pas lever : toutes les valeurs sont des types JSON de base.
        json.dumps(Settings().to_dict())

    def test_from_dict_ignores_unknown_keys(self):
        settings = Settings.from_dict({"unknown_key": 123, "opacity": 33})
        self.assertEqual(settings.opacity, 33)

    def test_from_dict_tolerates_invalid_enum(self):
        # Une valeur d'énumération invalide retombe sur le défaut.
        settings = Settings.from_dict({"export_format": "tiff"})
        self.assertEqual(settings.export_format, Settings().export_format)

    def test_from_dict_coerces_types(self):
        settings = Settings.from_dict({"opacity": "55", "png_compression": "9",
                                       "overwrite": 1})
        self.assertEqual(settings.opacity, 55.0)
        self.assertEqual(settings.png_compression, 9)
        self.assertIs(settings.overwrite, True)

    def test_from_dict_bad_value_keeps_default(self):
        settings = Settings.from_dict({"opacity": "not-a-number"})
        self.assertEqual(settings.opacity, Settings().opacity)


class TestSettingsManager(unittest.TestCase):
    def test_save_then_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = SettingsManager(tmp)
            settings = Settings()
            settings.suffix = "_persisted"
            settings.opacity = 12.0
            self.assertTrue(manager.save(settings))
            self.assertTrue(os.path.exists(manager.path))

            loaded = manager.load()
            self.assertEqual(loaded.suffix, "_persisted")
            self.assertEqual(loaded.opacity, 12.0)

    def test_load_missing_returns_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = SettingsManager(os.path.join(tmp, "does-not-exist"))
            loaded = manager.load()
            self.assertEqual(loaded.suffix, Settings().suffix)

    def test_load_corrupted_returns_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = SettingsManager(tmp)
            with open(manager.path, "w", encoding="utf-8") as handle:
                handle.write("{ this is not valid json ]")
            loaded = manager.load()
            self.assertIsInstance(loaded, Settings)
            self.assertEqual(loaded.opacity, Settings().opacity)

    def test_save_creates_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            nested = os.path.join(tmp, "a", "b", "c")
            manager = SettingsManager(nested)
            self.assertTrue(manager.save(Settings()))
            self.assertTrue(os.path.isdir(nested))


if __name__ == "__main__":
    unittest.main()
