# -*- coding: utf-8 -*-
"""Test de fumée exécuté **à l'intérieur de GIMP**.

Les tests de ``tests/test_*.py`` ne couvrent que la logique pure. Ce script-ci
vérifie ce qui ne peut l'être que face au vrai runtime : le pipeline complet
(duplication → filigrane → fusion → écriture PNG), le découpage en générateur
de :meth:`lib.exporter.BatchExporter.iter_export`, l'annulation propre en
cours de lot, et le bridage GEGL de :mod:`lib.perf`.

Lancement (voir ``scripts/offload.sh smoke``) ::

    gimp -i --batch-interpreter python-fu-eval \\
         -b "exec(open('/chemin/tests/smoke_gimp.py').read())"

Le script sort du processus avec un code non nul si une vérification échoue,
ce qui rend le résultat exploitable par un script d'intégration continue.
"""

import os
import shutil
import sys
import tempfile
import time
import traceback

import gi

gi.require_version("Gimp", "3.0")
gi.require_version("Gegl", "0.4")
from gi.repository import Gegl, Gimp  # noqa: E402

# Ce fichier est exécuté via exec() : ``__file__`` n'est pas toujours défini.
_HERE = os.path.dirname(os.path.realpath(
    globals().get("__file__") or os.path.join(os.getcwd(), "tests", "x")))
_PLUGIN_DIR = os.environ.get("SMOKE_PLUGIN_DIR") or os.path.dirname(_HERE)
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

from lib import perf  # noqa: E402
from lib.constants import ExportFormat, Position, SizeMode, WatermarkType  # noqa: E402
from lib.exporter import (  # noqa: E402
    EXPORTER_REGISTRY,
    BaseFormatExporter,
    BatchExporter,
    list_open_images,
)
from lib.settings import Settings  # noqa: E402

_FAILURES = []
_CHECKS = 0


def check(condition, label):
    """Vérifie une condition et journalise le verdict."""
    global _CHECKS
    _CHECKS += 1
    if condition:
        print(f"  ok   — {label}", flush=True)
    else:
        print(f"  FAIL — {label}", flush=True)
        _FAILURES.append(label)


def make_image(width, height, name):
    """Crée une image de test remplie (non affichée).

    Une image GIMP 3 sans fichier n'a pas de nom modifiable : le nom du calque
    tient lieu d'étiquette, l'export se rabattra sur « sans-titre » et son
    compteur d'unicité — ce qui fait aussi partie de ce qu'on veut vérifier.
    """
    image = Gimp.Image.new(width, height, Gimp.ImageBaseType.RGB)
    layer = Gimp.Layer.new(image, name, width, height,
                           Gimp.ImageType.RGB_IMAGE, 100.0, Gimp.LayerMode.NORMAL)
    image.insert_layer(layer, None, 0)
    layer.fill(Gimp.FillType.WHITE)
    return image


def base_settings(out_dir):
    """Préférences d'un export PNG avec filigrane texte."""
    settings = Settings()
    settings.watermark_type = WatermarkType.TEXT
    settings.watermark_text = "© Smoke Test"
    settings.text_size = 64.0
    settings.size_mode = SizeMode.PERCENT_WIDTH
    settings.size_value = 30.0
    settings.position = Position.BOTTOM_RIGHT
    settings.export_format = ExportFormat.PNG
    settings.output_dir = out_dir
    settings.use_source_folder = False
    settings.create_subfolder = False
    settings.skip_unmodified = False
    return settings


# ---------------------------------------------------------------------------
# Vérifications
# ---------------------------------------------------------------------------

def test_gegl_throttling():
    """Le bridage GEGL s'applique réellement, puis est restauré."""
    print("[1] Bridage GEGL", flush=True)
    config = Gegl.config()
    before = config.get_property("threads")
    print(f"  threads GEGL avant : {before} (machine : {perf.cpu_count()} cœurs)",
          flush=True)

    with perf.limited_resources(True, 1) as applied:
        during = config.get_property("threads")
        expected = perf.compute_worker_threads(perf.cpu_count(), 1)
        check(applied == expected or applied is None,
              f"bridage annoncé cohérent (appliqué={applied}, attendu={expected})")
        check(during == expected,
              f"threads GEGL bridés pendant l'export ({during} == {expected})")

    check(config.get_property("threads") == before,
          f"configuration GEGL restaurée après l'export ({before})")


def test_native_export_procedures(out_dir):
    """Chaque format s'exporte via sa vraie procédure PDB, sans repli.

    Le repli ``Gimp.file_save`` produit bien un fichier, mais avec les options
    par défaut : les réglages de compression/qualité de l'utilisateur seraient
    silencieusement perdus. On vérifie donc que le chemin natif est emprunté,
    puis que la compression PNG a un effet mesurable.
    """
    print("[2] Procédures d'export natives", flush=True)
    for export_format, exporter in EXPORTER_REGISTRY.items():
        found = None
        for name in exporter.procedures:
            if Gimp.get_pdb().lookup_procedure(name) is not None:
                found = name
                break
        check(found is not None,
              f"{export_format.value} : procédure PDB disponible "
              f"(candidats : {', '.join(exporter.procedures)})")
        if found:
            print(f"  procédure retenue pour {export_format.value} : {found}", flush=True)

    image = make_image(1200, 900, "native")
    settings = base_settings(out_dir)

    # Le repli doit rester inutilisé : on le piège le temps du test.
    fallback_calls = []
    original_fallback = BaseFormatExporter._export_fallback
    BaseFormatExporter._export_fallback = staticmethod(
        lambda img, gfile: fallback_calls.append(gfile.get_path()))
    try:
        sizes = {}
        for compression in (1, 9):
            settings.png_compression = compression
            settings.suffix = f"_c{compression}"
            results = BatchExporter(settings).export_all()
            written = [r.output_path for r in results if r.output_path]
            check(bool(written), f"fichier écrit avec compression={compression}")
            if written:
                sizes[compression] = os.path.getsize(written[0])
    finally:
        BaseFormatExporter._export_fallback = original_fallback

    check(not fallback_calls,
          f"export natif utilisé (repli déclenché : {fallback_calls})")
    if len(sizes) == 2:
        print(f"  tailles PNG : compression 1 → {sizes[1]} o, 9 → {sizes[9]} o",
              flush=True)
        check(sizes[9] < sizes[1],
              "le réglage de compression PNG atteint réellement GIMP")

    image.delete()


def test_full_pipeline(out_dir):
    """Le lot complet produit un PNG par image, en rendant la main entre chaque."""
    print("[3] Pipeline complet (3 images)", flush=True)
    images = [make_image(1600, 1200, f"smoke-{i}") for i in range(3)]
    check(len(list_open_images()) >= 3, "les images créées sont vues par le moteur")

    stages = []
    progress = []
    settings = base_settings(out_dir)

    started = time.time()
    exporter = BatchExporter(settings)
    results = []
    for result in exporter.iter_export(
            progress_callback=lambda i, t, n, s: progress.append((i, t, n, s)),
            stage_callback=stages.append):
        results.append(result)
        # Le générateur doit rendre la main APRÈS chaque image : c'est ici que
        # l'interface graphique repasserait dans sa boucle d'événements.
        print(f"  → rendu la main après {len(results)} image(s)", flush=True)
    elapsed = time.time() - started

    check(len(results) == len(images), f"un résultat par image ({len(results)})")
    check(all(r.success for r in results),
          "toutes les images exportées : "
          + "; ".join(r.error_message for r in results if not r.success))
    written = sorted(f for f in os.listdir(out_dir) if f.endswith(".png"))
    check(len(written) == len(images), f"fichiers PNG écrits : {written}")
    check(len(progress) == len(images), "rappel de progression appelé par image")
    check(stages.count("filigrane") == len(images),
          f"rappels d'étape émis pendant chaque image ({stages.count('filigrane')})")
    check("écriture" in stages, "étape d'écriture signalée avant l'export")
    print(f"  durée : {elapsed:.2f}s pour {len(images)} images", flush=True)

    for image in images:
        image.delete()


def test_cancellation(out_dir):
    """Fermer le générateur en cours de lot n'exporte pas la suite."""
    print("[4] Annulation en cours de lot", flush=True)
    images = [make_image(1200, 900, f"cancel-{i}") for i in range(3)]
    settings = base_settings(out_dir)

    config = Gegl.config()
    threads_before = config.get_property("threads")

    generator = BatchExporter(settings).iter_export()
    first = next(generator)
    check(first.success, "première image exportée avant l'annulation")
    check(config.get_property("threads")
          == perf.compute_worker_threads(perf.cpu_count(), settings.cpu_reserve),
          "bridage actif pendant le lot")

    generator.close()  # Ce que fait l'interface quand on clique « Annuler ».

    written = [f for f in os.listdir(out_dir) if f.endswith(".png")]
    check(len(written) == 1, f"une seule image écrite après annulation : {written}")
    check(config.get_property("threads") == threads_before,
          "charge GEGL restaurée même sur un lot interrompu")

    for image in images:
        image.delete()


# ---------------------------------------------------------------------------
# Exécution
# ---------------------------------------------------------------------------

def main():
    print(f"Test de fumée — GIMP {Gimp.version()} — plugin : {_PLUGIN_DIR}", flush=True)
    tmp_root = tempfile.mkdtemp(prefix="watermark-smoke-")
    try:
        test_gegl_throttling()
        native_dir = os.path.join(tmp_root, "native")
        os.makedirs(native_dir)
        test_native_export_procedures(native_dir)
        pipeline_dir = os.path.join(tmp_root, "pipeline")
        os.makedirs(pipeline_dir)
        test_full_pipeline(pipeline_dir)
        cancel_dir = os.path.join(tmp_root, "cancel")
        os.makedirs(cancel_dir)
        test_cancellation(cancel_dir)
    except Exception:
        traceback.print_exc()
        _FAILURES.append("exception non rattrapée")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    print("", flush=True)
    if _FAILURES:
        print(f"ÉCHEC — {len(_FAILURES)}/{_CHECKS} vérification(s) en erreur :", flush=True)
        for failure in _FAILURES:
            print(f"  • {failure}", flush=True)
    else:
        print(f"SUCCÈS — {_CHECKS} vérifications passées.", flush=True)
    return 1 if _FAILURES else 0


_EXIT_CODE = main()
# GIMP ne propage pas le code de retour du script : on écrit le verdict dans un
# fichier que le script appelant relit (voir scripts/offload.sh).
_VERDICT = os.environ.get("SMOKE_VERDICT_FILE")
if _VERDICT:
    with open(_VERDICT, "w", encoding="utf-8") as handle:
        handle.write(str(_EXIT_CODE))
