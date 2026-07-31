#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Moteur d'export par lot et registre d'exporteurs par format.

Ce module orchestre le traitement complet :

#. parcours de **toutes les images ouvertes** dans GIMP ;
#. duplication de chaque image (les originaux ne sont **jamais** modifiés) ;
#. application du filigrane sur la copie (délégué à :mod:`lib.watermark`) ;
#. aplatissement/fusion selon le format cible ;
#. export vers le disque via un exporteur spécialisé.

L'ajout d'un nouveau format d'export se limite à écrire une petite sous-classe
de :class:`BaseFormatExporter` et à l'enregistrer dans :data:`EXPORTER_REGISTRY`
(principe ouvert/fermé — aucune autre partie du code n'a besoin de changer).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Optional

import gi

gi.require_version("Gimp", "3.0")
from gi.repository import Gimp, Gio  # noqa: E402

from . import constants as C  # noqa: E402
from . import utils  # noqa: E402
from .constants import ExportFormat  # noqa: E402
from .logger import get_logger  # noqa: E402
from .settings import Settings  # noqa: E402
from .watermark import WatermarkError, WatermarkRenderer  # noqa: E402

_log = get_logger("exporter")

#: Signature d'un rappel de progression : ``(courant, total, nom, statut)``.
ProgressCallback = Callable[[int, int, str, str], None]


class ExportError(Exception):
    """Erreur survenue pendant l'écriture d'un fichier exporté."""


@dataclass
class ExportResult:
    """Résultat de l'export d'une image.

    :ivar image_name: nom de l'image source.
    :ivar output_path: chemin du fichier écrit (``None`` en cas d'échec).
    :ivar success: ``True`` si l'export a réussi.
    :ivar error_message: message d'erreur détaillé le cas échéant.
    """

    image_name: str
    output_path: Optional[str]
    success: bool
    error_message: str = ""


# ===========================================================================
# Exporteurs par format
# ===========================================================================

class BaseFormatExporter:
    """Classe de base d'un exporteur de format (contrat commun).

    Une sous-classe déclare son :attr:`format` et implémente
    :meth:`_export_native` (appel de la procédure PDB spécialisée). La méthode
    publique :meth:`export` ajoute une stratégie de **repli robuste** :
    si l'export natif échoue pour une raison quelconque, on retombe sur
    :func:`Gimp.file_save`, garantissant qu'un fichier est produit dès que
    possible.
    """

    #: Format géré par l'exporteur (redéfini par les sous-classes).
    format: ExportFormat = None  # type: ignore[assignment]

    def export(self, image: Gimp.Image, path: str, settings: Settings) -> None:
        """Écrit ``image`` vers ``path``.

        :raises ExportError: si l'export natif **et** le repli échouent.
        """
        gio_file = Gio.File.new_for_path(path)
        try:
            self._export_native(image, gio_file, settings)
            return
        except Exception as exc:  # noqa: BLE001 - on tente systématiquement le repli.
            _log.warning("Export natif %s échoué (%s) — repli sur file_save().",
                         self.format.value if self.format else "?", exc)
        self._export_fallback(image, gio_file)

    def _export_native(self, image: Gimp.Image, gio_file: Gio.File,
                       settings: Settings) -> None:
        """Export via la procédure PDB spécialisée (redéfini par les sous-classes)."""
        raise NotImplementedError

    @staticmethod
    def _export_fallback(image: Gimp.Image, gio_file: Gio.File) -> None:
        """Repli générique : :func:`Gimp.file_save` (options par défaut)."""
        ok = Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, image, gio_file, None)
        if not ok:
            raise ExportError(f"Échec de l'écriture de {gio_file.get_path()}")

    # -- utilitaire commun d'appel de procédure PDB -----------------------
    @staticmethod
    def _run_pdb_export(proc_name: str, image: Gimp.Image, gio_file: Gio.File,
                        extra_props: dict) -> None:
        """Exécute une procédure d'export PDB avec une configuration donnée.

        :param proc_name: nom de la procédure (ex. ``"file-png-save"``).
        :param extra_props: propriétés spécifiques au format (qualité…).
        :raises ExportError: si la procédure est absente ou renvoie un échec.

        Chaque affectation de propriété est protégée : une propriété inconnue
        (nom changé selon la version de GIMP) est ignorée sans interrompre
        l'export, ce qui rend le code tolérant aux évolutions de l'API.
        """
        proc = Gimp.get_pdb().lookup_procedure(proc_name)
        if proc is None:
            raise ExportError(f"Procédure d'export introuvable : {proc_name}")

        config = proc.create_config()

        def _set(name: str, value) -> None:
            try:
                config.set_property(name, value)
            except Exception:  # noqa: BLE001 - propriété absente/incompatible.
                _log.debug("Propriété d'export ignorée : %s.%s", proc_name, name)

        _set("run-mode", Gimp.RunMode.NONINTERACTIVE)
        _set("image", image)
        _set("file", gio_file)
        for key, value in extra_props.items():
            _set(key, value)

        result = proc.run(config)
        if result is None:
            raise ExportError(f"{proc_name} n'a renvoyé aucun résultat.")
        status = result.index(0)
        if status != Gimp.PDBStatusType.SUCCESS:
            raise ExportError(f"{proc_name} a échoué (statut={status}).")


class PngExporter(BaseFormatExporter):
    """Exporteur PNG (sans perte, transparence conservée)."""

    format = ExportFormat.PNG

    def _export_native(self, image, gio_file, settings):
        self._run_pdb_export("file-png-save", image, gio_file, {
            "compression": int(utils.clamp(settings.png_compression, 0, 9)),
        })


class JpegExporter(BaseFormatExporter):
    """Exporteur JPEG (avec réglage de qualité)."""

    format = ExportFormat.JPG

    def _export_native(self, image, gio_file, settings):
        # La qualité JPEG de la PDB GIMP 3 est un flottant 0.0–1.0.
        quality = utils.clamp(settings.jpeg_quality, 0, 100) / 100.0
        self._run_pdb_export("file-jpeg-save", image, gio_file, {
            "quality": quality,
        })


class WebpExporter(BaseFormatExporter):
    """Exporteur WebP (qualité + transparence)."""

    format = ExportFormat.WEBP

    def _export_native(self, image, gio_file, settings):
        # La qualité WebP de la PDB GIMP 3 est un flottant 0–100.
        self._run_pdb_export("file-webp-save", image, gio_file, {
            "quality": float(utils.clamp(settings.jpeg_quality, 0, 100)),
            "lossless": False,
        })


#: Registre des exporteurs disponibles, indexé par format.
#: Pour ajouter un format : créer la sous-classe puis l'enregistrer ici.
EXPORTER_REGISTRY: dict[ExportFormat, BaseFormatExporter] = {
    ExportFormat.PNG: PngExporter(),
    ExportFormat.JPG: JpegExporter(),
    ExportFormat.WEBP: WebpExporter(),
}


def get_exporter(export_format: ExportFormat) -> BaseFormatExporter:
    """Retourne l'exporteur associé à un format.

    :raises ExportError: si le format n'est pas pris en charge.
    """
    exporter = EXPORTER_REGISTRY.get(export_format)
    if exporter is None:
        raise ExportError(f"Format d'export non pris en charge : {export_format}")
    return exporter


# ===========================================================================
# Moteur de traitement par lot
# ===========================================================================

def list_open_images() -> list[Gimp.Image]:
    """Retourne la liste des images ouvertes **valides**."""
    return [img for img in Gimp.get_images() if img.is_valid()]


class BatchExporter:
    """Traite en lot toutes les images ouvertes.

    :param settings: préférences décrivant filigrane et export.
    :param renderer: moteur de filigrane (injectable pour les tests).

    L'objet ne modifie **jamais** les images d'origine : chaque image est
    dupliquée, filigranée sur la copie, exportée, puis la copie est détruite.
    Toute erreur sur une image est capturée et consignée dans un
    :class:`ExportResult`, sans jamais interrompre le traitement du lot.
    """

    def __init__(self, settings: Settings,
                 renderer: Optional[WatermarkRenderer] = None) -> None:
        self._settings = settings
        self._renderer = renderer or WatermarkRenderer()
        self._exporter = get_exporter(settings.export_format)
        self._extension = C.FORMAT_EXTENSIONS[settings.export_format]
        self._supports_alpha = C.FORMAT_SUPPORTS_ALPHA[settings.export_format]

    # ------------------------------------------------------------------ #
    def export_all(self, progress_callback: Optional[ProgressCallback] = None) -> list[ExportResult]:
        """Exporte toutes les images ouvertes et retourne les résultats.

        :param progress_callback: rappel invoqué après chaque image, avec
            ``(index_courant, total, nom_image, statut)``.
        :return: liste des :class:`ExportResult`, un par image traitée.
        """
        images = list_open_images()
        total = len(images)
        results: list[ExportResult] = []
        date_str = utils.today_string()

        _log.info("Début de l'export : %d image(s) ouverte(s).", total)
        Gimp.progress_init(f"{C.PLUGIN_TITLE} : 0/{total}")

        for index, image in enumerate(images, start=1):
            name = self._image_display_name(image)

            # Option : ignorer les images non modifiées.
            if self._settings.skip_unmodified and not image.is_dirty():
                _log.info("Image « %s » ignorée (non modifiée).", name)
                results.append(ExportResult(name, None, True, "Ignorée (non modifiée)"))
                self._report(progress_callback, index, total, name, "ignorée")
                continue

            result = self._process_one(image, name, date_str)
            results.append(result)
            self._report(progress_callback, index, total, name,
                         "ok" if result.success else "erreur")

        Gimp.progress_end()
        succeeded = sum(1 for r in results if r.success)
        _log.info("Export terminé : %d/%d réussi(s).", succeeded, total)
        return results

    # ------------------------------------------------------------------ #
    def _process_one(self, image: Gimp.Image, name: str, date_str: str) -> ExportResult:
        """Traite une image unique et retourne son résultat.

        Toutes les exceptions sont capturées : une image en échec n'empêche
        jamais le traitement des suivantes.
        """
        duplicate = None
        try:
            duplicate = image.duplicate()

            # 1. Application du filigrane sur la copie.
            self._renderer.apply(duplicate, self._settings)

            # 2. Fusion/aplatissement selon la prise en charge de l'alpha.
            if self._supports_alpha:
                duplicate.merge_visible_layers(Gimp.MergeType.CLIP_TO_IMAGE)
            else:
                duplicate.flatten()

            # 3. Détermination du chemin de sortie.
            out_dir = self._resolve_output_dir(image)
            os.makedirs(out_dir, exist_ok=True)

            stem = utils.build_output_stem(
                self._settings.naming_mode,
                original_stem=self._source_stem(image),
                date=date_str,
                width=duplicate.get_width(),
                height=duplicate.get_height(),
                prefix=self._settings.prefix,
                suffix=self._settings.suffix,
                custom_pattern=self._settings.custom_pattern,
            )
            out_path = utils.ensure_unique_path(
                out_dir, stem, self._extension, self._settings.overwrite,
            )

            # 4. Export.
            self._exporter.export(duplicate, out_path, self._settings)

            _log.info("Image « %s » exportée vers %s", name, out_path)
            return ExportResult(name, out_path, True)

        except (WatermarkError, ExportError) as exc:
            _log.error("Échec sur « %s » : %s", name, exc)
            return ExportResult(name, None, False, str(exc))
        except OSError as exc:
            _log.error("Erreur d'accès disque pour « %s » : %s", name, exc)
            return ExportResult(name, None, False, f"Accès disque : {exc}")
        except Exception as exc:  # noqa: BLE001 - filet de sécurité ultime.
            _log.exception("Erreur inattendue sur « %s »", name)
            return ExportResult(name, None, False, f"Erreur inattendue : {exc}")
        finally:
            if duplicate is not None:
                duplicate.delete()

    # ------------------------------------------------------------------ #
    # Helpers de nommage / dossier
    # ------------------------------------------------------------------ #
    @staticmethod
    def _image_display_name(image: Gimp.Image) -> str:
        """Nom lisible d'une image (nom de fichier ou titre GIMP)."""
        gfile = image.get_file()
        if gfile is not None and gfile.get_path():
            return os.path.basename(gfile.get_path())
        return image.get_name() or "sans-titre"

    @staticmethod
    def _source_stem(image: Gimp.Image) -> str:
        """Nom de base (sans extension) de l'image source."""
        gfile = image.get_file()
        if gfile is not None and gfile.get_path():
            base = os.path.basename(gfile.get_path())
            return os.path.splitext(base)[0]
        return utils.sanitize_filename(image.get_name() or "sans-titre")

    def _resolve_output_dir(self, image: Gimp.Image) -> str:
        """Détermine le dossier de sortie pour une image donnée."""
        settings = self._settings
        source_dir = None
        gfile = image.get_file()
        if gfile is not None and gfile.get_path():
            source_dir = os.path.dirname(gfile.get_path())

        if settings.use_source_folder and source_dir:
            base_dir = source_dir
        elif settings.output_dir:
            base_dir = settings.output_dir
        else:
            # Dernier recours pour une image sans fichier ni dossier choisi.
            base_dir = source_dir or os.path.expanduser("~")

        if settings.create_subfolder:
            base_dir = os.path.join(base_dir, C.EXPORTS_SUBFOLDER_NAME)
        return base_dir

    # ------------------------------------------------------------------ #
    @staticmethod
    def _report(callback: Optional[ProgressCallback], index: int, total: int,
                name: str, status: str) -> None:
        """Met à jour la progression GIMP puis notifie l'interface."""
        fraction = index / total if total else 1.0
        try:
            Gimp.progress_update(fraction)
            Gimp.progress_set_text(f"{index}/{total} : {name}")
        except Exception:  # noqa: BLE001 - la progression ne doit jamais bloquer.
            pass
        if callback is not None:
            callback(index, total, name, status)
