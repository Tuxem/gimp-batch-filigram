#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Maîtrise de la charge machine pendant un export par lot.

Un export de plusieurs images lourdes sature facilement la machine : GEGL (le
moteur de traitement de GIMP) parallélise ses opérations sur **tous** les cœurs
disponibles, ce qui rend le poste peu utilisable pendant le lot et allonge le
temps pendant lequel le plug-in ne rend pas la main.

Ce module fournit un garde-fou minimal et **réversible** : le temps de l'export,
on réduit le nombre de threads GEGL de façon à laisser quelques cœurs au reste
du système, puis on restaure la configuration d'origine.

Deux principes de conception :

* la partie **calculatoire** (:func:`compute_worker_threads`) est pure, donc
  testable sans GIMP ;
* la partie **effet de bord** (:func:`limited_resources`) importe GEGL
  paresseusement et n'échoue jamais : si la configuration n'est pas modifiable
  (version de GEGL différente, propriété absente…), l'export se déroule
  normalement, simplement sans bridage.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator, Optional

from .logger import get_logger

_log = get_logger("perf")

#: Propriété de :class:`GeglConfig` pilotant le parallélisme.
_THREADS_PROPERTY = "threads"


def cpu_count() -> int:
    """Retourne le nombre de cœurs utilisables (au moins 1)."""
    try:
        # Respecte l'affinité du processus quand la plateforme la fournit.
        return max(1, len(os.sched_getaffinity(0)))  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        return max(1, os.cpu_count() or 1)


def compute_worker_threads(cpus: int, reserve: int) -> int:
    """Nombre de threads GEGL à autoriser.

    :param cpus: nombre de cœurs de la machine.
    :param reserve: nombre de cœurs à laisser libres.
    :return: un entier **toujours >= 1** et <= ``cpus``.

    Réserver plus de cœurs qu'il n'en existe ne bloque pas l'export : on
    retombe sur un seul thread plutôt que sur zéro (ce qui figerait GEGL).
    """
    cpus = max(1, int(cpus))
    reserve = max(0, int(reserve))
    return max(1, cpus - reserve)


def _gegl_config():
    """Retourne l'objet de configuration GEGL, ou ``None`` s'il est indisponible."""
    try:
        import gi

        gi.require_version("Gegl", "0.4")
        from gi.repository import Gegl  # noqa: PLC0415 - import paresseux volontaire.

        return Gegl.config()
    except Exception as exc:  # noqa: BLE001 - le bridage est un confort, pas un prérequis.
        _log.debug("Configuration GEGL inaccessible (%s) — bridage ignoré.", exc)
        return None


@contextmanager
def limited_resources(enabled: bool, reserve: int) -> Iterator[Optional[int]]:
    """Bride le parallélisme de GEGL le temps du bloc, puis le restaure.

    :param enabled: si ``False``, le contexte ne fait strictement rien.
    :param reserve: nombre de cœurs à laisser libres.
    :yield: le nombre de threads effectivement appliqué, ou ``None`` si aucun
        bridage n'a pu être mis en place.

    La restauration est garantie (``finally``), y compris si le bloc lève ou si
    le générateur appelant est fermé prématurément (annulation de l'export).
    """
    if not enabled:
        yield None
        return

    config = _gegl_config()
    if config is None:
        yield None
        return

    previous = None
    applied = None
    try:
        previous = config.get_property(_THREADS_PROPERTY)
        threads = compute_worker_threads(cpu_count(), reserve)
        if threads != previous:
            config.set_property(_THREADS_PROPERTY, threads)
            applied = threads
            _log.info("Charge bridée : %d thread(s) GEGL (au lieu de %s).",
                      threads, previous)
    except Exception as exc:  # noqa: BLE001 - propriété absente/incompatible.
        _log.debug("Bridage GEGL impossible (%s) — export à pleine charge.", exc)
        previous = None

    try:
        yield applied
    finally:
        if applied is not None and previous is not None:
            try:
                config.set_property(_THREADS_PROPERTY, previous)
                _log.debug("Configuration GEGL restaurée (%s thread(s)).", previous)
            except Exception as exc:  # noqa: BLE001
                _log.debug("Restauration GEGL impossible (%s).", exc)
