#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Installateur multiplateforme du plugin *Watermark Exporter*.

Ce script copie le plugin dans le dossier de plug-ins utilisateur de GIMP 3.x,
en respectant la règle de GIMP 3 : un plug-in Python doit résider dans un
sous-dossier portant **le même nom** que son script principal
(``watermark_exporter/watermark_exporter.py``) et ce script doit être
exécutable.

Utilisation ::

    python3 install.py                 # installe (détection automatique)
    python3 install.py --uninstall     # désinstalle
    python3 install.py --force         # écrase sans confirmation
    python3 install.py --plugins-dir /chemin/vers/plug-ins
    python3 install.py --gimp-version 3.2

Le script fonctionne sous Linux, Windows et macOS. Il n'a **aucune dépendance**
en dehors de la bibliothèque standard Python et n'a pas besoin que GIMP soit en
cours d'exécution.
"""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import sys

#: Nom du dossier/plugin (doit correspondre au script principal).
PLUGIN_NAME = "watermark_exporter"

#: Éléments copiés lors de l'installation.
INSTALL_ITEMS = ("watermark_exporter.py", "lib", "resources")

#: Versions GIMP 3.x connues, de la plus récente à la plus ancienne.
KNOWN_VERSIONS = ("3.2", "3.0")


# ---------------------------------------------------------------------------
# Détection des chemins
# ---------------------------------------------------------------------------

def gimp_config_base() -> str:
    """Retourne le dossier de configuration GIMP racine selon le système.

    :return: chemin du dossier contenant les sous-dossiers de version
        (``3.0``, ``3.2``…).
    """
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
        return os.path.join(appdata, "GIMP")
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library",
                            "Application Support", "GIMP")
    # Linux / BSD : respecte XDG_CONFIG_HOME.
    xdg = os.environ.get("XDG_CONFIG_HOME", os.path.join(os.path.expanduser("~"), ".config"))
    return os.path.join(xdg, "GIMP")


def detect_gimp_version(base: str, forced: str | None) -> str:
    """Détermine la version de configuration GIMP à cibler.

    :param base: dossier de configuration racine de GIMP.
    :param forced: version imposée en ligne de commande, ou ``None``.
    :return: numéro de version (ex. ``"3.2"``).

    Priorité : version forcée > version existante la plus récente > version la
    plus récente connue (créée si nécessaire).
    """
    if forced:
        return forced
    if os.path.isdir(base):
        existing = [v for v in KNOWN_VERSIONS if os.path.isdir(os.path.join(base, v))]
        if existing:
            return existing[0]
    return KNOWN_VERSIONS[0]


def resolve_plugins_dir(args: argparse.Namespace) -> str:
    """Calcule le dossier ``plug-ins`` utilisateur cible."""
    if args.plugins_dir:
        return os.path.abspath(args.plugins_dir)
    base = gimp_config_base()
    version = detect_gimp_version(base, args.gimp_version)
    return os.path.join(base, version, "plug-ins")


# ---------------------------------------------------------------------------
# Opérations d'installation
# ---------------------------------------------------------------------------

def make_executable(path: str) -> None:
    """Ajoute le bit exécutable à un fichier (utile sous Linux/macOS)."""
    current = os.stat(path).st_mode
    os.chmod(path, current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def install(source_dir: str, target_root: str, force: bool) -> int:
    """Installe le plugin dans ``target_root/<PLUGIN_NAME>``.

    :return: code de sortie (0 = succès).
    """
    target = os.path.join(target_root, PLUGIN_NAME)

    if os.path.exists(target):
        if not force:
            answer = input(f"Le plugin existe déjà dans « {target} ». Écraser ? [o/N] ")
            if answer.strip().lower() not in ("o", "oui", "y", "yes"):
                print("Installation annulée.")
                return 1
        shutil.rmtree(target, ignore_errors=True)

    try:
        os.makedirs(target, exist_ok=True)
        for item in INSTALL_ITEMS:
            src = os.path.join(source_dir, item)
            if not os.path.exists(src):
                print(f"Avertissement : élément absent, ignoré : {item}")
                continue
            dst = os.path.join(target, item)
            if os.path.isdir(src):
                shutil.copytree(
                    src, dst,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                )
            else:
                shutil.copy2(src, dst)

        # Le script principal doit être exécutable.
        make_executable(os.path.join(target, "watermark_exporter.py"))
    except OSError as exc:
        print(f"Erreur pendant l'installation : {exc}", file=sys.stderr)
        return 2

    print("✓ Plugin installé avec succès dans :")
    print(f"    {target}")
    print()
    print("Redémarrez GIMP, puis ouvrez :")
    print("    Fichier ▸ Exporter toutes les images avec filigrane…")
    return 0


def uninstall(target_root: str) -> int:
    """Supprime le plugin installé.

    :return: code de sortie (0 = succès).
    """
    target = os.path.join(target_root, PLUGIN_NAME)
    if not os.path.exists(target):
        print(f"Aucune installation trouvée dans « {target} ».")
        return 0
    try:
        shutil.rmtree(target)
    except OSError as exc:
        print(f"Erreur pendant la désinstallation : {exc}", file=sys.stderr)
        return 2
    print(f"✓ Plugin désinstallé : {target}")
    return 0


# ---------------------------------------------------------------------------
# Point d'entrée CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Construit l'analyseur d'arguments en ligne de commande."""
    parser = argparse.ArgumentParser(
        description="Installe ou désinstalle le plugin GIMP « Watermark Exporter ».")
    parser.add_argument("--uninstall", action="store_true",
                        help="désinstalle le plugin au lieu de l'installer")
    parser.add_argument("--force", action="store_true",
                        help="écrase une installation existante sans confirmation")
    parser.add_argument("--plugins-dir", default=None,
                        help="chemin explicite du dossier plug-ins de GIMP")
    parser.add_argument("--gimp-version", default=None,
                        help="version GIMP à cibler (ex. 3.2) ; détection auto par défaut")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée principal du script d'installation."""
    args = build_parser().parse_args(argv)
    source_dir = os.path.dirname(os.path.realpath(__file__))
    target_root = resolve_plugins_dir(args)

    print(f"Dossier plug-ins cible : {target_root}")
    if args.uninstall:
        return uninstall(target_root)
    return install(source_dir, target_root, args.force)


if __name__ == "__main__":
    raise SystemExit(main())
