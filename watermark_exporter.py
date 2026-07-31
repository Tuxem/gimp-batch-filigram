#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Point d'entrée du plugin GIMP 3.2.x *Watermark Exporter*.

Ce fichier enregistre la procédure auprès de GIMP et orchestre le lancement :
il charge les préférences, initialise la journalisation, puis affiche
l'interface (mode interactif) ou lance directement le traitement (mode non
interactif / batch).

Toute la logique métier est déléguée aux modules du paquet :mod:`lib`, ce qui
maintient ce fichier volontairement mince (principe de responsabilité unique).

Installation : voir :mod:`install` ou le ``README.md``. En résumé, GIMP 3.x
exige que ce script réside dans un dossier de même nom
(``watermark_exporter/watermark_exporter.py``), au sein d'un des dossiers de
plug-ins de l'utilisateur, et qu'il soit exécutable.
"""

from __future__ import annotations

import os
import sys

# GIMP lance ce script directement : on ajoute son dossier au chemin de
# recherche pour pouvoir importer le paquet local ``lib``.
_PLUGIN_DIR = os.path.dirname(os.path.realpath(__file__))
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

import gi

gi.require_version("Gimp", "3.0")
gi.require_version("Gegl", "0.4")
from gi.repository import Gimp, GLib  # noqa: E402

from lib import constants as C  # noqa: E402
from lib.exporter import BatchExporter, list_open_images  # noqa: E402
from lib.logger import configure_logging, get_logger  # noqa: E402
from lib.settings import SettingsManager  # noqa: E402


def _config_dir() -> str:
    """Retourne le dossier de configuration du plugin (dans le dossier GIMP)."""
    return os.path.join(Gimp.directory(), C.PLUGIN_ID)


class WatermarkExporter(Gimp.PlugIn):
    """Déclaration et exécution de la procédure GIMP.

    La classe suit le contrat des plug-ins Python de GIMP 3 : ``do_*`` pour la
    déclaration, plus une fonction ``run`` pour l'exécution.
    """

    # -- Déclaration ------------------------------------------------------
    def do_query_procedures(self) -> list[str]:
        """Liste les procédures fournies par ce plug-in."""
        return [C.PROCEDURE_NAME]

    def do_set_i18n(self, _procname: str):
        """Désactive la traduction (les chaînes sont utilisées telles quelles).

        Retourner ``False`` évite toute dépendance à un catalogue gettext
        manquant, garantissant un affichage correct sur toutes les installations.
        """
        return False

    def do_create_procedure(self, name: str) -> Gimp.Procedure:
        """Construit et configure la procédure enregistrée."""
        procedure = Gimp.ImageProcedure.new(
            self, name, Gimp.PDBProcType.PLUGIN, self.run, None)

        procedure.set_image_types("*")
        procedure.set_menu_label(C.MENU_LABEL)
        procedure.add_menu_path(C.MENU_PATH)
        procedure.set_documentation(
            "Exporte toutes les images ouvertes en appliquant un filigrane.",
            "Applique un filigrane (image PNG ou texte) à une copie de chaque "
            "image ouverte, puis exporte le résultat (PNG, JPEG ou WebP). Les "
            "images originales ne sont jamais modifiées.",
            name,
        )
        procedure.set_attribution(C.PLUGIN_AUTHORS, C.PLUGIN_COPYRIGHT, C.PLUGIN_YEAR)
        return procedure

    # -- Exécution --------------------------------------------------------
    def run(self, procedure, run_mode, image, drawables, config, run_data):
        """Fonction exécutée lorsque l'utilisateur active la procédure.

        :param run_mode: mode d'exécution (interactif ou non).
        :return: valeurs de retour PDB (statut de succès/annulation/erreur).

        L'ensemble du corps est protégé : quelle que soit l'erreur, la
        procédure retourne un statut valide plutôt que de laisser remonter une
        exception (le plugin ne doit jamais planter).
        """
        config_dir = _config_dir()
        manager = SettingsManager(config_dir)
        settings = manager.load()
        logger = configure_logging(config_dir, settings.debug)

        try:
            images = list_open_images()
            if not images:
                Gimp.message("Aucune image ouverte : ouvrez au moins une image "
                             "avant de lancer l'export avec filigrane.")
                return procedure.new_return_values(
                    Gimp.PDBStatusType.CANCEL, GLib.Error())

            if run_mode == Gimp.RunMode.INTERACTIVE:
                status = self._run_interactive(procedure, manager, settings, images)
            else:
                status = self._run_headless(settings)

            Gimp.displays_flush()
            return procedure.new_return_values(status, GLib.Error())

        except Exception as exc:  # noqa: BLE001 - filet de sécurité ultime.
            logger.exception("Erreur fatale dans la procédure")
            Gimp.message(f"Erreur inattendue : {exc}")
            return procedure.new_return_values(
                Gimp.PDBStatusType.EXECUTION_ERROR,
                GLib.Error(str(exc)))

    # ------------------------------------------------------------------ #
    @staticmethod
    def _run_interactive(procedure, manager: SettingsManager, settings, images) -> "Gimp.PDBStatusType":
        """Affiche l'interface GTK et lance l'export à la demande."""
        import gi
        gi.require_version("GimpUi", "3.0")
        from gi.repository import GimpUi

        from lib.ui import WatermarkDialog

        GimpUi.init(C.PROCEDURE_NAME)

        def runner(current_settings, progress_callback, stage_callback):
            # Forme *générateur* : le dialogue fait avancer l'export image par
            # image depuis la boucle GTK, ce qui garde la fenêtre réactive
            # (voir la note d'en-tête de lib.ui).
            return BatchExporter(current_settings).iter_export(
                progress_callback, stage_callback)

        dialog = WatermarkDialog(settings, manager, runner, len(images))
        dialog.run()
        return Gimp.PDBStatusType.SUCCESS

    @staticmethod
    def _run_headless(settings) -> "Gimp.PDBStatusType":
        """Lance l'export sans interface, avec les préférences enregistrées."""
        logger = get_logger()
        logger.info("Exécution non interactive : utilisation des préférences enregistrées.")
        results = BatchExporter(settings).export_all()
        failed = [r for r in results if not r.success]
        if failed:
            return Gimp.PDBStatusType.EXECUTION_ERROR
        return Gimp.PDBStatusType.SUCCESS


Gimp.main(WatermarkExporter.__gtype__, sys.argv)
