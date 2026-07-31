#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fonctions utilitaires **pures** du plugin.

Ce module regroupe toute la logique « calculatoire » qui ne dépend pas de
GIMP : géométrie (redimensionnement, positionnement, marges), génération des
noms de fichiers et validation des paramètres.

Le fait de garder ces fonctions pures (entrées → sortie, sans effet de bord ni
dépendance à GObject/Gimp) présente deux avantages majeurs :

* elles sont **entièrement testables** par des tests unitaires classiques ;
* elles sont **réutilisables** et faciles à raisonner (responsabilité unique).
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Iterable

from . import constants as C
from .constants import (
    ExportFormat,
    NamingMode,
    Position,
    SizeMode,
    WatermarkType,
)


# ---------------------------------------------------------------------------
# Petits helpers numériques
# ---------------------------------------------------------------------------

def clamp(value: float, minimum: float, maximum: float) -> float:
    """Contraint ``value`` dans l'intervalle ``[minimum, maximum]``.

    :param value: valeur à borner.
    :param minimum: borne inférieure.
    :param maximum: borne supérieure.
    :return: la valeur bornée.
    """
    if value < minimum:
        return minimum
    if value > maximum:
        return maximum
    return value


# ---------------------------------------------------------------------------
# Géométrie : redimensionnement du filigrane
# ---------------------------------------------------------------------------

def compute_scaled_size(
    base_width: int,
    base_height: int,
    watermark_width: int,
    watermark_height: int,
    size_mode: SizeMode,
    size_value: float,
) -> tuple[int, int]:
    """Calcule la taille cible du filigrane en **conservant le ratio**.

    :param base_width: largeur de l'image de base (px).
    :param base_height: hauteur de l'image de base (px).
    :param watermark_width: largeur native du filigrane (px).
    :param watermark_height: hauteur native du filigrane (px).
    :param size_mode: mode de calcul (largeur %, hauteur % ou taille fixe).
    :param size_value: valeur associée au mode (% ou pixels).
    :return: couple ``(largeur, hauteur)`` cible, chaque valeur ``>= 1``.
    :raises ValueError: si les dimensions natives du filigrane sont invalides.

    Le ratio d'aspect natif du filigrane est toujours préservé : on calcule une
    dimension de référence puis on déduit l'autre proportionnellement.
    """
    if watermark_width <= 0 or watermark_height <= 0:
        raise ValueError("Les dimensions du filigrane doivent être positives.")

    ratio = watermark_width / watermark_height

    if size_mode is SizeMode.PERCENT_WIDTH:
        target_w = base_width * (size_value / 100.0)
        target_h = target_w / ratio
    elif size_mode is SizeMode.PERCENT_HEIGHT:
        target_h = base_height * (size_value / 100.0)
        target_w = target_h * ratio
    elif size_mode is SizeMode.FIXED:
        # La taille fixe est interprétée comme la *largeur* cible en pixels.
        target_w = float(size_value)
        target_h = target_w / ratio
    else:  # pragma: no cover - garde-fou défensif.
        raise ValueError(f"Mode de taille inconnu : {size_mode!r}")

    # On garantit au minimum 1 px pour éviter un filigrane invisible/invalide.
    return max(1, int(round(target_w))), max(1, int(round(target_h)))


# ---------------------------------------------------------------------------
# Géométrie : marges
# ---------------------------------------------------------------------------

def resolve_margin(
    margin_value: float,
    margin_is_percent: bool,
    base_width: int,
    base_height: int,
) -> tuple[int, int]:
    """Résout une marge (fixe ou en pourcentage) en pixels.

    :param margin_value: valeur de la marge (px ou %).
    :param margin_is_percent: ``True`` si ``margin_value`` est un pourcentage.
    :param base_width: largeur de l'image de base (px).
    :param base_height: hauteur de l'image de base (px).
    :return: couple ``(marge_x, marge_y)`` en pixels.

    En mode pourcentage, la marge horizontale est relative à la largeur et la
    marge verticale à la hauteur, ce qui donne un rendu visuellement équilibré
    quelle que soit la forme de l'image.
    """
    if margin_is_percent:
        margin_x = base_width * (margin_value / 100.0)
        margin_y = base_height * (margin_value / 100.0)
    else:
        margin_x = margin_y = margin_value
    return int(round(margin_x)), int(round(margin_y))


# ---------------------------------------------------------------------------
# Géométrie : position
# ---------------------------------------------------------------------------

def compute_position(
    position: Position,
    base_width: int,
    base_height: int,
    watermark_width: int,
    watermark_height: int,
    margin_x: int,
    margin_y: int,
    custom_x: int = 0,
    custom_y: int = 0,
) -> tuple[int, int]:
    """Calcule le décalage (coin supérieur gauche) du filigrane sur l'image.

    :param position: l'une des neuf positions classiques ou ``CUSTOM``.
    :param base_width: largeur de l'image de base (px).
    :param base_height: hauteur de l'image de base (px).
    :param watermark_width: largeur finale du filigrane (px).
    :param watermark_height: hauteur finale du filigrane (px).
    :param margin_x: marge horizontale (px).
    :param margin_y: marge verticale (px).
    :param custom_x: abscisse explicite si ``position`` vaut ``CUSTOM``.
    :param custom_y: ordonnée explicite si ``position`` vaut ``CUSTOM``.
    :return: couple ``(x, y)`` du coin supérieur gauche du filigrane.

    Les ancres (0 = début, 1 = centre, 2 = fin) portées par l'énumération
    :class:`~lib.constants.Position` permettent un calcul unifié sans longue
    cascade de conditions.
    """
    if position is Position.CUSTOM:
        return int(custom_x), int(custom_y)

    anchor_x, anchor_y = position.anchors

    # Positions horizontales possibles selon l'ancre.
    x_by_anchor = {
        0: margin_x,
        1: (base_width - watermark_width) // 2,
        2: base_width - watermark_width - margin_x,
    }
    y_by_anchor = {
        0: margin_y,
        1: (base_height - watermark_height) // 2,
        2: base_height - watermark_height - margin_y,
    }
    return int(x_by_anchor[anchor_x]), int(y_by_anchor[anchor_y])


# ---------------------------------------------------------------------------
# Nommage des fichiers exportés
# ---------------------------------------------------------------------------

#: Caractères interdits dans un nom de fichier (compatibilité multiplateforme).
_ILLEGAL_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_filename(name: str) -> str:
    """Nettoie un nom de fichier pour qu'il soit valide sur tous les OS.

    :param name: nom brut potentiellement dangereux.
    :return: nom nettoyé (jamais vide).

    Les caractères réservés Windows/Unix sont remplacés par ``_`` et les
    espaces de début/fin ainsi que les points terminaux (interdits sous
    Windows) sont supprimés.
    """
    cleaned = _ILLEGAL_FILENAME_CHARS.sub("_", name)
    cleaned = cleaned.strip().strip(".")
    return cleaned or "image"


def today_string(fmt: str = "%Y-%m-%d") -> str:
    """Retourne la date du jour formatée (par défaut ``AAAA-MM-JJ``)."""
    return datetime.now().strftime(fmt)


def render_filename(
    pattern: str,
    *,
    filename: str,
    date: str,
    width: int,
    height: int,
    prefix: str = "",
    suffix: str = "",
) -> str:
    """Génère un nom de fichier (sans extension) à partir d'un motif.

    :param pattern: motif contenant éventuellement des variables
        ``{filename}``, ``{date}``, ``{width}``, ``{height}``, ``{prefix}`` et
        ``{suffix}``.
    :param filename: nom de base de l'image d'origine (sans extension).
    :param date: chaîne de date déjà formatée.
    :param width: largeur de l'image exportée (px).
    :param height: hauteur de l'image exportée (px).
    :param prefix: préfixe utilisateur.
    :param suffix: suffixe utilisateur.
    :return: nom de fichier nettoyé, sans extension.

    Une variable inconnue dans le motif est laissée telle quelle plutôt que de
    provoquer une exception : la génération de nom ne doit jamais faire échouer
    un export.
    """
    values = {
        "filename": filename,
        "date": date,
        "width": width,
        "height": height,
        "prefix": prefix,
        "suffix": suffix,
    }
    try:
        rendered = pattern.format(**values)
    except (KeyError, IndexError, ValueError):
        # Motif contenant une variable inconnue ou des accolades malformées :
        # on effectue un remplacement tolérant, variable par variable.
        rendered = pattern
        for key, value in values.items():
            rendered = rendered.replace("{" + key + "}", str(value))
    return sanitize_filename(rendered)


def build_output_stem(
    naming_mode: NamingMode,
    *,
    original_stem: str,
    date: str,
    width: int,
    height: int,
    prefix: str = "",
    suffix: str = "",
    custom_pattern: str = "",
) -> str:
    """Construit le nom de sortie (sans extension) selon le mode de nommage.

    :param naming_mode: stratégie de nommage choisie.
    :param original_stem: nom de base de l'image d'origine (sans extension).
    :param date: chaîne de date déjà formatée.
    :param width: largeur exportée.
    :param height: hauteur exportée.
    :param prefix: préfixe utilisateur.
    :param suffix: suffixe utilisateur.
    :param custom_pattern: motif libre (utilisé uniquement en mode ``CUSTOM``).
    :return: nom de fichier nettoyé, sans extension.
    """
    if naming_mode is NamingMode.CUSTOM and custom_pattern.strip():
        pattern = custom_pattern
    else:
        pattern = C.NAMING_PATTERNS[naming_mode]

    return render_filename(
        pattern,
        filename=original_stem,
        date=date,
        width=width,
        height=height,
        prefix=prefix,
        suffix=suffix,
    )


def ensure_unique_path(
    directory: str,
    stem: str,
    extension: str,
    overwrite: bool,
) -> str:
    """Construit un chemin de sortie, en évitant l'écrasement si demandé.

    :param directory: dossier de destination.
    :param stem: nom de fichier sans extension.
    :param extension: extension sans point (ex. ``"png"``).
    :param overwrite: si ``True``, retourne directement le chemin (écrasement
        autorisé) ; sinon, un suffixe numérique ``_1``, ``_2``… est ajouté
        jusqu'à trouver un nom libre.
    :return: chemin absolu de sortie.
    """
    base = os.path.join(directory, f"{stem}.{extension}")
    if overwrite or not os.path.exists(base):
        return base

    counter = 1
    while True:
        candidate = os.path.join(directory, f"{stem}_{counter}.{extension}")
        if not os.path.exists(candidate):
            return candidate
        counter += 1


# ---------------------------------------------------------------------------
# Validation des paramètres
# ---------------------------------------------------------------------------

def validate_export_parameters(
    *,
    watermark_type: WatermarkType,
    watermark_path: str,
    watermark_text: str,
    opacity: float,
    size_value: float,
    margin_value: float,
    output_dir: str,
    use_source_folder: bool,
    export_format: ExportFormat,
) -> list[str]:
    """Valide un jeu de paramètres et retourne la liste des erreurs.

    :return: liste de messages d'erreur (vide si tout est valide).

    Cette fonction ne lève jamais d'exception : elle accumule les problèmes
    afin que l'interface puisse tous les présenter d'un coup à l'utilisateur.
    """
    errors: list[str] = []

    if watermark_type is WatermarkType.IMAGE:
        if not watermark_path:
            errors.append("Aucun fichier de filigrane (logo PNG) n'a été sélectionné.")
        elif not os.path.isfile(watermark_path):
            errors.append(f"Le fichier de filigrane est introuvable : {watermark_path}")
    elif watermark_type is WatermarkType.TEXT:
        if not watermark_text.strip():
            errors.append("Le texte du filigrane est vide.")

    if not (C.OPACITY_MIN <= opacity <= C.OPACITY_MAX):
        errors.append(
            f"L'opacité doit être comprise entre {int(C.OPACITY_MIN)} et "
            f"{int(C.OPACITY_MAX)} % (valeur reçue : {opacity})."
        )

    if size_value <= 0:
        errors.append("La taille du filigrane doit être strictement positive.")

    if margin_value < 0:
        errors.append("La marge ne peut pas être négative.")

    if not isinstance(export_format, ExportFormat):
        errors.append("Le format d'export sélectionné est invalide.")

    if not use_source_folder:
        if not output_dir:
            errors.append("Aucun dossier de sortie n'a été sélectionné.")
        elif not os.path.isdir(output_dir):
            errors.append(f"Le dossier de sortie n'existe pas : {output_dir}")

    return errors


def iter_pattern_variables(pattern: str) -> Iterable[str]:
    """Itère sur les noms de variables ``{var}`` présents dans un motif.

    Utilitaire de commodité (par ex. pour valider/mettre en surbrillance un
    motif dans l'interface). Les variables inconnues sont incluses telles
    quelles ; c'est à l'appelant de les filtrer via
    :data:`lib.constants.NAMING_VARIABLES` si besoin.
    """
    return re.findall(r"\{(\w+)\}", pattern)
