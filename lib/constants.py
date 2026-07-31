#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Constantes et énumérations du plugin *Watermark Exporter*.

Ce module est volontairement **exempt de toute dépendance à GIMP / GObject**.
Il ne contient que des valeurs pures (chaînes, énumérations, dictionnaires),
ce qui le rend :

* trivialement importable dans les tests unitaires (aucun runtime GIMP requis) ;
* stable et centralisé (une seule source de vérité pour toutes les clés).

Toute la configuration textuelle et énumérée du plugin transite par ici afin
d'éviter la duplication de « chaînes magiques » dans le reste du code.
"""

from __future__ import annotations

import enum


# ---------------------------------------------------------------------------
# Métadonnées du plugin
# ---------------------------------------------------------------------------

#: Nom court, utilisé comme identifiant technique (dossiers, logs, domaine i18n).
PLUGIN_ID: str = "watermark-exporter"

#: Nom de la procédure enregistrée dans la PDB de GIMP.
PROCEDURE_NAME: str = "python-fu-watermark-exporter"

#: Nom lisible du plugin (affiché dans les titres de fenêtre).
PLUGIN_TITLE: str = "Exporter toutes les images avec filigrane"

#: Version sémantique du plugin.
PLUGIN_VERSION: str = "1.0.0"

#: Auteur / attribution (repris dans set_attribution).
PLUGIN_AUTHORS: str = "Watermark Exporter contributors"
PLUGIN_COPYRIGHT: str = "GPL-3.0-or-later"
PLUGIN_YEAR: str = "2026"

#: Emplacement du menu dans GIMP (menu « Fichier »).
MENU_PATH: str = "<Image>/File/"

#: Libellé de l'entrée de menu.
MENU_LABEL: str = "Exporter toutes les images avec _filigrane..."


# ---------------------------------------------------------------------------
# Énumérations métier
# ---------------------------------------------------------------------------

class WatermarkType(enum.Enum):
    """Type de filigrane à appliquer."""

    IMAGE = "image"   #: Filigrane à partir d'un fichier PNG transparent.
    TEXT = "text"     #: Filigrane texte généré dynamiquement.


class Position(enum.Enum):
    """Les neuf positions classiques + une position personnalisée.

    La valeur de chaque membre est un couple ``(ancre_horizontale,
    ancre_verticale)`` où chaque ancre vaut ``0`` (début), ``1`` (centre) ou
    ``2`` (fin). ``CUSTOM`` porte la valeur ``None`` : les coordonnées sont
    alors fournies explicitement.
    """

    TOP_LEFT = (0, 0)
    TOP_CENTER = (1, 0)
    TOP_RIGHT = (2, 0)
    MIDDLE_LEFT = (0, 1)
    CENTER = (1, 1)
    MIDDLE_RIGHT = (2, 1)
    BOTTOM_LEFT = (0, 2)
    BOTTOM_CENTER = (1, 2)
    BOTTOM_RIGHT = (2, 2)
    CUSTOM = None

    @property
    def anchors(self) -> tuple[int, int]:
        """Retourne le couple d'ancres, ``(1, 1)`` (centre) pour ``CUSTOM``."""
        return self.value if self.value is not None else (1, 1)


#: Libellés utilisateur (français) associés à chaque position.
POSITION_LABELS: dict[Position, str] = {
    Position.TOP_LEFT: "Haut gauche",
    Position.TOP_CENTER: "Haut centre",
    Position.TOP_RIGHT: "Haut droite",
    Position.MIDDLE_LEFT: "Centre gauche",
    Position.CENTER: "Centre",
    Position.MIDDLE_RIGHT: "Centre droite",
    Position.BOTTOM_LEFT: "Bas gauche",
    Position.BOTTOM_CENTER: "Bas centre",
    Position.BOTTOM_RIGHT: "Bas droite",
    Position.CUSTOM: "Coordonnées personnalisées",
}


class SizeMode(enum.Enum):
    """Mode de calcul de la taille du filigrane."""

    PERCENT_WIDTH = "percent_width"    #: % de la largeur de l'image de base.
    PERCENT_HEIGHT = "percent_height"  #: % de la hauteur de l'image de base.
    FIXED = "fixed"                    #: Largeur cible fixe en pixels.


SIZE_MODE_LABELS: dict[SizeMode, str] = {
    SizeMode.PERCENT_WIDTH: "Pourcentage de la largeur",
    SizeMode.PERCENT_HEIGHT: "Pourcentage de la hauteur",
    SizeMode.FIXED: "Taille fixe (pixels)",
}


class NamingMode(enum.Enum):
    """Stratégie de nommage des fichiers exportés."""

    SAME = "same"       #: Nom identique à l'original.
    PREFIX = "prefix"   #: Préfixe + nom original.
    SUFFIX = "suffix"   #: Nom original + suffixe.
    DATE = "date"       #: Date + nom original.
    CUSTOM = "custom"   #: Motif personnalisé (variables).


NAMING_MODE_LABELS: dict[NamingMode, str] = {
    NamingMode.SAME: "Nom identique",
    NamingMode.PREFIX: "Préfixe",
    NamingMode.SUFFIX: "Suffixe",
    NamingMode.DATE: "Date",
    NamingMode.CUSTOM: "Personnalisé",
}

#: Motif de nom associé à chaque mode. Les variables disponibles sont
#: ``{filename}``, ``{date}``, ``{width}``, ``{height}``, ``{prefix}`` et
#: ``{suffix}``.
NAMING_PATTERNS: dict[NamingMode, str] = {
    NamingMode.SAME: "{filename}",
    NamingMode.PREFIX: "{prefix}{filename}",
    NamingMode.SUFFIX: "{filename}{suffix}",
    NamingMode.DATE: "{date}_{filename}",
    NamingMode.CUSTOM: "{filename}",  # remplacé par le motif utilisateur.
}

#: Ensemble des variables reconnues dans un motif de nom.
NAMING_VARIABLES: tuple[str, ...] = ("filename", "date", "width", "height",
                                     "prefix", "suffix")


class ExportFormat(enum.Enum):
    """Formats d'export pris en charge.

    L'ajout d'un nouveau format se fait ici **et** dans le registre
    d'exporteurs de :mod:`lib.exporter`. Aucune autre modification n'est
    nécessaire (principe ouvert/fermé).
    """

    PNG = "png"
    JPG = "jpg"
    WEBP = "webp"


#: Extension de fichier (sans point) associée à chaque format.
FORMAT_EXTENSIONS: dict[ExportFormat, str] = {
    ExportFormat.PNG: "png",
    ExportFormat.JPG: "jpg",
    ExportFormat.WEBP: "webp",
}

#: Indique si le format supporte un canal alpha (transparence).
FORMAT_SUPPORTS_ALPHA: dict[ExportFormat, bool] = {
    ExportFormat.PNG: True,
    ExportFormat.JPG: False,
    ExportFormat.WEBP: True,
}

FORMAT_LABELS: dict[ExportFormat, str] = {
    ExportFormat.PNG: "PNG (sans perte, transparence)",
    ExportFormat.JPG: "JPEG (compressé)",
    ExportFormat.WEBP: "WebP (moderne)",
}


# ---------------------------------------------------------------------------
# Bornes et valeurs par défaut
# ---------------------------------------------------------------------------

OPACITY_MIN: float = 0.0
OPACITY_MAX: float = 100.0
OPACITY_DEFAULT: float = 70.0

ROTATION_MIN: float = -360.0
ROTATION_MAX: float = 360.0
ROTATION_DEFAULT: float = 0.0

SIZE_VALUE_DEFAULT: float = 15.0     #: 15 % de la largeur par défaut.
SIZE_FIXED_DEFAULT: float = 350.0    #: 350 px si mode FIXED.

MARGIN_DEFAULT: float = 20.0         #: 20 px de marge par défaut.

JPEG_QUALITY_DEFAULT: int = 90       #: Qualité JPEG/WebP (0-100).
PNG_COMPRESSION_DEFAULT: int = 6     #: Compression PNG (0-9).

#: Nom du sous-dossier créé automatiquement si l'option est activée.
EXPORTS_SUBFOLDER_NAME: str = "exports"

#: Nom du fichier de préférences (stocké dans le dossier de config de GIMP).
SETTINGS_FILENAME: str = "settings.json"

#: Nom du fichier journal.
LOG_FILENAME: str = "watermark-exporter.log"
