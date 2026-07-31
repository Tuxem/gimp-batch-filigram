# -*- coding: utf-8 -*-
"""Tests unitaires des fonctions pures de :mod:`lib.utils`.

Couvre : redimensionnement, marges, calcul de position, génération et unicité
des noms de fichiers, nettoyage et validation des paramètres.
"""

import os
import sys
import tempfile
import unittest

# Permet d'exécuter les tests depuis la racine du projet.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from lib import utils
from lib.constants import (
    ExportFormat,
    NamingMode,
    Position,
    SizeMode,
    WatermarkType,
)


class TestClamp(unittest.TestCase):
    def test_within_range(self):
        self.assertEqual(utils.clamp(5, 0, 10), 5)

    def test_below_and_above(self):
        self.assertEqual(utils.clamp(-3, 0, 10), 0)
        self.assertEqual(utils.clamp(42, 0, 10), 10)


class TestScaledSize(unittest.TestCase):
    """Le ratio d'aspect natif du filigrane doit toujours être conservé."""

    def test_percent_width(self):
        # 15 % de 1000 px = 150 px de large ; ratio 2:1 -> 75 px de haut.
        self.assertEqual(
            utils.compute_scaled_size(1000, 800, 400, 200, SizeMode.PERCENT_WIDTH, 15),
            (150, 75),
        )

    def test_percent_height(self):
        # 12 % de 800 px = 96 px de haut ; ratio 2:1 -> 192 px de large.
        self.assertEqual(
            utils.compute_scaled_size(1000, 800, 400, 200, SizeMode.PERCENT_HEIGHT, 12),
            (192, 96),
        )

    def test_fixed_width(self):
        # Taille fixe interprétée comme largeur cible.
        self.assertEqual(
            utils.compute_scaled_size(1000, 800, 400, 200, SizeMode.FIXED, 350),
            (350, 175),
        )

    def test_ratio_preserved_non_integer(self):
        w, h = utils.compute_scaled_size(1000, 1000, 333, 100, SizeMode.PERCENT_WIDTH, 30)
        self.assertEqual(w, 300)
        # 300 * (100/333) ~ 90.09 -> arrondi 90.
        self.assertEqual(h, 90)

    def test_minimum_one_pixel(self):
        w, h = utils.compute_scaled_size(10, 10, 400, 200, SizeMode.PERCENT_WIDTH, 0.01)
        self.assertGreaterEqual(w, 1)
        self.assertGreaterEqual(h, 1)

    def test_invalid_watermark_dimensions(self):
        with self.assertRaises(ValueError):
            utils.compute_scaled_size(100, 100, 0, 10, SizeMode.FIXED, 50)


class TestMargins(unittest.TestCase):
    def test_pixel_margin(self):
        self.assertEqual(utils.resolve_margin(20, False, 1000, 800), (20, 20))

    def test_percent_margin(self):
        # 5 % de 1000 = 50 ; 5 % de 800 = 40.
        self.assertEqual(utils.resolve_margin(5, True, 1000, 800), (50, 40))


class TestPosition(unittest.TestCase):
    """Vérifie les neuf positions classiques + la position personnalisée."""

    BASE_W, BASE_H = 1000, 800
    WM_W, WM_H = 100, 50
    MX, MY = 20, 30

    def _pos(self, position):
        return utils.compute_position(
            position, self.BASE_W, self.BASE_H, self.WM_W, self.WM_H, self.MX, self.MY)

    def test_top_left(self):
        self.assertEqual(self._pos(Position.TOP_LEFT), (20, 30))

    def test_top_center(self):
        self.assertEqual(self._pos(Position.TOP_CENTER), (450, 30))

    def test_top_right(self):
        self.assertEqual(self._pos(Position.TOP_RIGHT), (880, 30))

    def test_middle_left(self):
        self.assertEqual(self._pos(Position.MIDDLE_LEFT), (20, 375))

    def test_center(self):
        self.assertEqual(self._pos(Position.CENTER), (450, 375))

    def test_middle_right(self):
        self.assertEqual(self._pos(Position.MIDDLE_RIGHT), (880, 375))

    def test_bottom_left(self):
        self.assertEqual(self._pos(Position.BOTTOM_LEFT), (20, 720))

    def test_bottom_center(self):
        self.assertEqual(self._pos(Position.BOTTOM_CENTER), (450, 720))

    def test_bottom_right(self):
        self.assertEqual(self._pos(Position.BOTTOM_RIGHT), (880, 720))

    def test_custom(self):
        result = utils.compute_position(
            Position.CUSTOM, self.BASE_W, self.BASE_H, self.WM_W, self.WM_H,
            self.MX, self.MY, custom_x=123, custom_y=456)
        self.assertEqual(result, (123, 456))


class TestFilenameGeneration(unittest.TestCase):
    def test_same(self):
        self.assertEqual(
            utils.build_output_stem(NamingMode.SAME, original_stem="photo",
                                    date="2026-08-01", width=10, height=20),
            "photo",
        )

    def test_suffix(self):
        self.assertEqual(
            utils.build_output_stem(NamingMode.SUFFIX, original_stem="photo",
                                    date="2026-08-01", width=10, height=20,
                                    suffix="_watermark"),
            "photo_watermark",
        )

    def test_prefix(self):
        self.assertEqual(
            utils.build_output_stem(NamingMode.PREFIX, original_stem="photo",
                                    date="2026-08-01", width=10, height=20,
                                    prefix="wm_"),
            "wm_photo",
        )

    def test_date(self):
        self.assertEqual(
            utils.build_output_stem(NamingMode.DATE, original_stem="photo",
                                    date="2026-08-01", width=10, height=20),
            "2026-08-01_photo",
        )

    def test_custom_pattern_variables(self):
        self.assertEqual(
            utils.build_output_stem(NamingMode.CUSTOM, original_stem="photo",
                                    date="2026-08-01", width=640, height=480,
                                    custom_pattern="{filename}_{width}x{height}_{date}"),
            "photo_640x480_2026-08-01",
        )

    def test_custom_pattern_unknown_variable_is_tolerated(self):
        # Une variable inconnue ne doit pas faire échouer la génération.
        result = utils.build_output_stem(
            NamingMode.CUSTOM, original_stem="photo", date="d", width=1, height=2,
            custom_pattern="{filename}_{unknown}")
        self.assertIn("photo", result)

    def test_sanitize_removes_illegal_chars(self):
        # 6 caractères illégaux après « c » : * ? " < > |
        self.assertEqual(utils.sanitize_filename('a/b:c*?"<>|.png'), "a_b_c______.png")

    def test_sanitize_never_empty(self):
        self.assertTrue(utils.sanitize_filename("///"))


class TestUniquePath(unittest.TestCase):
    def test_returns_direct_when_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = utils.ensure_unique_path(tmp, "photo", "png", overwrite=False)
            self.assertEqual(path, os.path.join(tmp, "photo.png"))

    def test_overwrite_returns_same_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            existing = os.path.join(tmp, "photo.png")
            open(existing, "w").close()
            path = utils.ensure_unique_path(tmp, "photo", "png", overwrite=True)
            self.assertEqual(path, existing)

    def test_no_overwrite_adds_counter(self):
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "photo.png"), "w").close()
            open(os.path.join(tmp, "photo_1.png"), "w").close()
            path = utils.ensure_unique_path(tmp, "photo", "png", overwrite=False)
            self.assertEqual(path, os.path.join(tmp, "photo_2.png"))


class TestValidation(unittest.TestCase):
    def _valid_kwargs(self, **overrides):
        base = dict(
            watermark_type=WatermarkType.TEXT,
            watermark_path="",
            watermark_text="© Test",
            opacity=70,
            size_value=15,
            margin_value=20,
            output_dir="",
            use_source_folder=True,
            export_format=ExportFormat.PNG,
        )
        base.update(overrides)
        return base

    def test_valid_text_config(self):
        self.assertEqual(utils.validate_export_parameters(**self._valid_kwargs()), [])

    def test_missing_logo_for_image_mode(self):
        errors = utils.validate_export_parameters(
            **self._valid_kwargs(watermark_type=WatermarkType.IMAGE, watermark_path=""))
        self.assertTrue(any("filigrane" in e.lower() for e in errors))

    def test_empty_text(self):
        errors = utils.validate_export_parameters(**self._valid_kwargs(watermark_text="   "))
        self.assertTrue(any("texte" in e.lower() for e in errors))

    def test_opacity_out_of_range(self):
        errors = utils.validate_export_parameters(**self._valid_kwargs(opacity=150))
        self.assertTrue(any("opacité" in e.lower() for e in errors))

    def test_non_positive_size(self):
        errors = utils.validate_export_parameters(**self._valid_kwargs(size_value=0))
        self.assertTrue(any("taille" in e.lower() for e in errors))

    def test_negative_margin(self):
        errors = utils.validate_export_parameters(**self._valid_kwargs(margin_value=-1))
        self.assertTrue(any("marge" in e.lower() for e in errors))

    def test_missing_output_dir_when_not_source(self):
        errors = utils.validate_export_parameters(
            **self._valid_kwargs(use_source_folder=False, output_dir=""))
        self.assertTrue(any("dossier" in e.lower() for e in errors))


if __name__ == "__main__":
    unittest.main()
