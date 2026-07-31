#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Paquet interne du plugin *Watermark Exporter*.

Ce paquet regroupe la logique du plugin, découpée par responsabilité :

* :mod:`lib.constants`  — constantes et énumérations (sans dépendance GIMP) ;
* :mod:`lib.utils`      — fonctions pures (géométrie, noms, validation) ;
* :mod:`lib.settings`   — modèle de préférences et persistance JSON ;
* :mod:`lib.logger`     — configuration de la journalisation ;
* :mod:`lib.watermark`  — rendu du filigrane (dépend de GIMP) ;
* :mod:`lib.exporter`   — moteur d'export par lot (dépend de GIMP) ;
* :mod:`lib.ui`         — interface graphique GTK 3 (dépend de GIMP/GTK).

Les quatre premiers modules sont volontairement exempts de toute dépendance à
GIMP afin de rester testables unitairement sans lancer l'application.
"""

__all__ = [
    "constants",
    "utils",
    "settings",
    "logger",
    "watermark",
    "exporter",
    "ui",
]

__version__ = "1.0.0"
