#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Configuration centralisée de la journalisation du plugin.

Le plugin ne doit **jamais planter silencieusement** : chaque étape importante
et chaque erreur sont journalisées, à la fois dans un fichier tournant (pour le
support / le débogage) et sur la sortie d'erreur (visible dans la console
lorsque GIMP est lancé depuis un terminal).

Niveaux utilisés : ``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``.

Ce module est indépendant de GIMP (il n'importe que la bibliothèque standard),
ce qui le rend testable et réutilisable. Le dossier des journaux est fourni par
l'appelant.
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from . import constants as C

#: Nom racine du logger du plugin. Tous les loggers de modules en dérivent.
_ROOT_LOGGER_NAME = C.PLUGIN_ID

_LOG_FORMAT = "%(asctime)s [%(levelname)-7s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

#: Drapeau interne évitant d'installer plusieurs fois les handlers.
_configured = False


def configure_logging(log_dir: str | None = None, debug: bool = False) -> logging.Logger:
    """Configure (une seule fois) le logger racine du plugin.

    :param log_dir: dossier où écrire le fichier journal. Si ``None`` ou
        inaccessible, seule la sortie console est utilisée.
    :param debug: si ``True``, le niveau ``DEBUG`` est activé, sinon ``INFO``.
    :return: le logger racine configuré.

    Appeler cette fonction plusieurs fois est sans danger : les handlers ne
    sont installés qu'au premier appel, les appels suivants se contentent
    d'ajuster le niveau de verbosité.
    """
    global _configured

    logger = logging.getLogger(_ROOT_LOGGER_NAME)
    level = logging.DEBUG if debug else logging.INFO
    logger.setLevel(level)
    # Empêche la propagation vers le root logger de Python (double affichage).
    logger.propagate = False

    if _configured:
        # Réglage a posteriori du niveau (ex. activation du mode debug).
        for handler in logger.handlers:
            handler.setLevel(level)
        return logger

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # --- Handler console (stderr) ---------------------------------------
    console = logging.StreamHandler(stream=sys.stderr)
    console.setFormatter(formatter)
    console.setLevel(level)
    logger.addHandler(console)

    # --- Handler fichier tournant (best effort) -------------------------
    if log_dir:
        try:
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, C.LOG_FILENAME)
            file_handler = RotatingFileHandler(
                log_path,
                maxBytes=1_000_000,   # ~1 Mo par fichier.
                backupCount=3,        # 3 archives conservées.
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            file_handler.setLevel(logging.DEBUG)  # Le fichier garde tout.
            logger.addHandler(file_handler)
        except OSError:
            # Impossible d'écrire le fichier : on continue avec la console seule.
            logger.warning("Impossible d'initialiser le journal fichier dans %s", log_dir)

    _configured = True
    logger.debug("Journalisation initialisée (niveau=%s, dossier=%s)",
                 logging.getLevelName(level), log_dir)
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Retourne un logger enfant du logger racine du plugin.

    :param name: nom court du module (ex. ``"exporter"``). Si ``None``, le
        logger racine est retourné.
    :return: le logger correspondant.
    """
    if not name:
        return logging.getLogger(_ROOT_LOGGER_NAME)
    return logging.getLogger(f"{_ROOT_LOGGER_NAME}.{name}")
