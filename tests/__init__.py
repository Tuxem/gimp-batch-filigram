# -*- coding: utf-8 -*-
"""Suite de tests unitaires du plugin *Watermark Exporter*.

Ces tests ne ciblent que la logique **pure** (sans dépendance à GIMP) :
géométrie, génération de noms, validation et persistance des préférences. Ils
s'exécutent donc avec un simple interpréteur Python, sans lancer GIMP ::

    python3 -m unittest discover -s tests -v
    # ou, si pytest est installé :
    python3 -m pytest tests -v
"""
