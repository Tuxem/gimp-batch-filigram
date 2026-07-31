#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Modèle de préférences et persistance du plugin.

Les préférences sont sérialisées en **JSON** dans le dossier de configuration
de GIMP (``Gimp.directory()``). Ce format est :

* lisible et éditable par un humain (débogage aisé) ;
* portable entre Linux, Windows et macOS ;
* indépendant de tout runtime graphique (donc testable unitairement).

Le module reste **exempt de dépendance à GIMP** : le chemin du dossier de
configuration est *injecté* par l'appelant. Cela permet d'exécuter les tests
sans lancer GIMP, tout en respectant le principe d'inversion de dépendance.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields

from . import constants as C
from .constants import (
    ExportFormat,
    NamingMode,
    Position,
    SizeMode,
    WatermarkType,
)

# Mapping nom-d'énumération → classe, pour la (dé)sérialisation générique.
_ENUM_TYPES = {
    "watermark_type": WatermarkType,
    "position": Position,
    "size_mode": SizeMode,
    "naming_mode": NamingMode,
    "export_format": ExportFormat,
}


@dataclass
class Settings:
    """Ensemble complet des préférences du plugin.

    Chaque attribut correspond à un réglage de l'interface. Les valeurs par
    défaut proviennent de :mod:`lib.constants` afin de centraliser la
    configuration. Les champs de type énuméré sont manipulés en tant
    qu'énumérations en mémoire et sérialisés via leur ``.value`` en JSON.
    """

    # --- Filigrane -------------------------------------------------------
    watermark_type: WatermarkType = WatermarkType.IMAGE
    watermark_path: str = ""                 #: Dernier logo PNG utilisé.
    watermark_text: str = "© Mon Studio"

    # Options du filigrane texte.
    text_font: str = "Sans-serif Bold"
    text_size: float = 48.0
    text_color: str = "#ffffff"              #: Couleur hex #rrggbb.
    text_outline: bool = True
    text_outline_color: str = "#000000"
    text_outline_width: int = 2
    text_shadow: bool = True
    text_shadow_color: str = "#000000"
    text_shadow_offset: int = 4

    # --- Placement / apparence ------------------------------------------
    opacity: float = C.OPACITY_DEFAULT
    size_mode: SizeMode = SizeMode.PERCENT_WIDTH
    size_value: float = C.SIZE_VALUE_DEFAULT
    rotation: float = C.ROTATION_DEFAULT
    position: Position = Position.BOTTOM_RIGHT
    custom_x: int = 0
    custom_y: int = 0
    margin_value: float = C.MARGIN_DEFAULT
    margin_is_percent: bool = False

    # --- Export ----------------------------------------------------------
    export_format: ExportFormat = ExportFormat.PNG
    jpeg_quality: int = C.JPEG_QUALITY_DEFAULT
    png_compression: int = C.PNG_COMPRESSION_DEFAULT

    output_dir: str = ""                     #: Dernier dossier de sortie.
    use_source_folder: bool = False          #: Exporter à côté de l'original.
    create_subfolder: bool = True            #: Créer un sous-dossier « exports ».

    # --- Nommage ---------------------------------------------------------
    naming_mode: NamingMode = NamingMode.SUFFIX
    prefix: str = ""
    suffix: str = "_watermark"
    custom_pattern: str = "{filename}_{date}"
    overwrite: bool = False

    # --- Traitement ------------------------------------------------------
    skip_unmodified: bool = False            #: Ignorer les images non modifiées.
    debug: bool = False                      #: Activer les logs DEBUG.

    # ------------------------------------------------------------------ #
    # Sérialisation
    # ------------------------------------------------------------------ #
    def to_dict(self) -> dict:
        """Convertit les préférences en dictionnaire JSON-compatible.

        Les énumérations sont réduites à leur ``.value`` (chaîne).
        """
        data = asdict(self)
        for name in _ENUM_TYPES:
            value = getattr(self, name)
            data[name] = value.value
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        """Reconstruit des préférences depuis un dictionnaire.

        La méthode est **tolérante** : les clés inconnues sont ignorées, les
        clés manquantes prennent la valeur par défaut, et une valeur d'énum
        invalide retombe sur la valeur par défaut du champ. Ainsi un fichier de
        préférences corrompu ou issu d'une ancienne version ne fait jamais
        planter le plugin.
        """
        known = {f.name for f in fields(cls)}
        instance = cls()

        for key, value in data.items():
            if key not in known:
                continue
            if key in _ENUM_TYPES:
                enum_cls = _ENUM_TYPES[key]
                try:
                    setattr(instance, key, enum_cls(value))
                except ValueError:
                    # Valeur d'énumération inconnue : on garde le défaut.
                    continue
            else:
                # Coercition de type douce basée sur la valeur par défaut.
                default = getattr(instance, key)
                try:
                    if isinstance(default, bool):
                        setattr(instance, key, bool(value))
                    elif isinstance(default, int):
                        setattr(instance, key, int(value))
                    elif isinstance(default, float):
                        setattr(instance, key, float(value))
                    else:
                        setattr(instance, key, value)
                except (TypeError, ValueError):
                    continue
        return instance


class SettingsManager:
    """Charge et enregistre les :class:`Settings` sur le disque.

    :param config_dir: dossier où stocker le fichier de préférences (en
        production, un sous-dossier de ``Gimp.directory()``).

    Le dossier est créé à la volée si nécessaire. Toutes les opérations
    d'entrée/sortie sont protégées : une erreur de lecture/écriture est
    silencieusement neutralisée (retour aux valeurs par défaut) afin de ne
    jamais interrompre le fonctionnement du plugin.
    """

    def __init__(self, config_dir: str) -> None:
        self._config_dir = config_dir
        self._path = os.path.join(config_dir, C.SETTINGS_FILENAME)

    @property
    def path(self) -> str:
        """Chemin absolu du fichier de préférences."""
        return self._path

    def load(self) -> Settings:
        """Charge les préférences, ou retourne les valeurs par défaut.

        :return: une instance de :class:`Settings` toujours valide.
        """
        try:
            with open(self._path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                return Settings()
            return Settings.from_dict(data)
        except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
            return Settings()

    def save(self, settings: Settings) -> bool:
        """Enregistre les préférences sur le disque.

        :param settings: préférences à persister.
        :return: ``True`` en cas de succès, ``False`` sinon.

        L'écriture est **atomique** (fichier temporaire puis renommage) afin de
        ne jamais laisser un fichier de préférences tronqué en cas
        d'interruption.
        """
        try:
            os.makedirs(self._config_dir, exist_ok=True)
            tmp_path = f"{self._path}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as handle:
                json.dump(settings.to_dict(), handle, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self._path)
            return True
        except OSError:
            return False
