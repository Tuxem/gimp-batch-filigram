# -*- coding: utf-8 -*-
"""Tests unitaires du bridage de charge (:mod:`lib.perf`).

Seule la partie **pure** est testée ici : le module doit rester importable et
utilisable sans runtime GIMP/GEGL (l'effet de bord réel est vérifié par le
test de fumée exécuté dans GIMP, ``tests/smoke_gimp.py``).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from lib import perf


class TestComputeWorkerThreads(unittest.TestCase):
    def test_reserves_requested_cores(self):
        self.assertEqual(perf.compute_worker_threads(12, 1), 11)
        self.assertEqual(perf.compute_worker_threads(12, 4), 8)

    def test_zero_reserve_uses_every_core(self):
        self.assertEqual(perf.compute_worker_threads(8, 0), 8)

    def test_never_returns_less_than_one(self):
        # Réserver autant (ou plus) de cœurs qu'il n'en existe ne doit jamais
        # aboutir à 0 thread : GEGL serait bloqué.
        self.assertEqual(perf.compute_worker_threads(4, 4), 1)
        self.assertEqual(perf.compute_worker_threads(4, 99), 1)
        self.assertEqual(perf.compute_worker_threads(1, 1), 1)

    def test_tolerates_absurd_inputs(self):
        self.assertEqual(perf.compute_worker_threads(0, 0), 1)
        self.assertEqual(perf.compute_worker_threads(-5, -5), 1)

    def test_accepts_float_like_values(self):
        # Les valeurs viennent de spin buttons GTK (float) ou du JSON.
        self.assertEqual(perf.compute_worker_threads(12.0, 2.0), 10)


class TestCpuCount(unittest.TestCase):
    def test_is_a_positive_integer(self):
        count = perf.cpu_count()
        self.assertIsInstance(count, int)
        self.assertGreaterEqual(count, 1)


class TestLimitedResources(unittest.TestCase):
    def test_disabled_is_a_noop(self):
        with perf.limited_resources(False, 1) as applied:
            self.assertIsNone(applied)

    def test_enabled_without_gegl_does_not_raise(self):
        # Hors de GIMP, la configuration GEGL est inaccessible : le contexte
        # doit se contenter de ne rien brider, sans jamais lever.
        with perf.limited_resources(True, 1) as applied:
            self.assertIn(applied, (None, perf.compute_worker_threads(perf.cpu_count(), 1)))

    def test_exception_inside_block_propagates(self):
        with self.assertRaises(ValueError):
            with perf.limited_resources(True, 1):
                raise ValueError("boom")


if __name__ == "__main__":
    unittest.main()
