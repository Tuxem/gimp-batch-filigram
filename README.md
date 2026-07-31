<!-- markdownlint-disable MD033 MD041 -->
<p align="center">
  <img src="resources/icon.svg" width="96" alt="Watermark Exporter" />
</p>

<h1 align="center">Watermark Exporter — plugin GIMP 3.2.x</h1>

<p align="center">
  <strong>Exportez en une seule opération toutes les images ouvertes dans GIMP,
  avec application automatique d'un filigrane.</strong>
</p>

<p align="center">
  <img alt="GIMP 3.2.x" src="https://img.shields.io/badge/GIMP-3.2.x-5c5543" />
  <img alt="Python 3" src="https://img.shields.io/badge/Python-3-3776ab" />
  <img alt="GTK 3" src="https://img.shields.io/badge/GTK-3-4a90d9" />
  <img alt="Licence GPL-3.0" src="https://img.shields.io/badge/Licence-GPL--3.0-blue" />
</p>

---

## Sommaire

- [Aperçu](#aperçu)
- [Fonctionnalités](#fonctionnalités)
- [Captures d'écran](#captures-décran)
- [Installation](#installation)
  - [Prérequis](#prérequis)
  - [Installation automatique (recommandée)](#installation-automatique-recommandée)
  - [Linux](#linux)
  - [Windows](#windows)
  - [macOS](#macos)
- [Utilisation](#utilisation)
- [Dépannage](#dépannage)
- [FAQ](#faq)
- [Développement](#développement)
- [Architecture](#architecture)
- [Contribution](#contribution)
- [Licence](#licence)

---

## Aperçu

**Watermark Exporter** ajoute à GIMP une entrée de menu **_Fichier ▸ Exporter
toutes les images avec filigrane…_** qui traite en lot toutes les images
actuellement ouvertes :

1. chaque image est **dupliquée** (les originaux ne sont **jamais** modifiés) ;
2. un **filigrane** (logo PNG ou texte) est appliqué à la copie ;
3. le résultat est **exporté** au format choisi (PNG, JPEG ou WebP) dans le
   dossier de destination, selon une règle de nommage configurable.

Le plugin est écrit exclusivement avec les **API officielles de GIMP 3**
(`gi.repository.Gimp`, `GimpUi`, `Gegl`, `GLib`, `Gio`, `GObject`). Aucune API
Python-Fu de GIMP 2.x n'est utilisée.

> ### 🛈 Note technique : GTK 3 et non GTK 4
>
> GIMP 3.2.x est une application **GTK 3** : son module `GimpUi` est lié à
> `Gtk-3.0` (vérifiable dans la typelib). Or, un même processus **ne peut pas**
> charger simultanément GTK 3 et GTK 4. L'interface d'un plugin GIMP 3.2 doit
> donc obligatoirement utiliser **GTK 3**. Ce plugin s'appuie sur GTK 3 tout en
> visant un rendu moderne (fenêtre à en-tête, onglets, contrôles cohérents). Un
> portage GTK 4 ne deviendra pertinent que lorsque GIMP lui-même migrera vers
> GTK 4. Le code est structuré pour rendre ce futur portage aussi indolore que
> possible (toute l'interface est isolée dans `lib/ui.py`).

---

## Fonctionnalités

| Catégorie          | Détails                                                                                  |
|--------------------|------------------------------------------------------------------------------------------|
| **Images**         | Traite toutes les images ouvertes ; ignore les images invalides ou (optionnellement) non modifiées ; barre de progression. |
| **Filigrane image**| Logo PNG transparent, transparence conservée, redimensionnement automatique à ratio constant, opacité réglable. |
| **Filigrane texte**| Police, taille, couleur, opacité, **contour**, **ombre portée** floutée.                 |
| **Position**       | 9 positions classiques + coordonnées **X/Y personnalisées**.                             |
| **Taille**         | % de la largeur, % de la hauteur, ou taille **fixe** en pixels.                          |
| **Marges**         | En pixels ou en pourcentage.                                                             |
| **Rotation**       | Angle libre (ex. `0°`, `15°`, `45°`, `-20°`).                                            |
| **Opacité**        | De 0 à 100 %.                                                                            |
| **Export**         | PNG, JPEG, WebP — architecture extensible (registre d'exporteurs).                       |
| **Nommage**        | Identique, préfixe, suffixe, date, ou motif libre : `{filename} {date} {width} {height}`.|
| **Sortie**         | Dossier au choix ou à côté de l'original ; création automatique d'un dossier `exports`.  |
| **Préférences**    | Mémorisées (JSON) : dernier logo, dernier dossier, opacité, taille, format, position…    |
| **Robustesse**     | Gestion d'erreurs complète ; le plugin ne plante jamais ; journalisation + mode debug.   |

---

## Captures d'écran

> _Les captures ci-dessous sont des emplacements réservés. Remplacez les
> fichiers dans `resources/screenshots/` par vos propres images._

| Onglet Filigrane | Onglet Export | Progression |
|------------------|---------------|-------------|
| ![Filigrane](resources/screenshots/01-watermark.png) | ![Export](resources/screenshots/02-export.png) | ![Progression](resources/screenshots/03-progress.png) |

---

## Installation

### Prérequis

- **GIMP 3.2.x** (testé avec GIMP 3.2.2).
- Le support **Python** de GIMP (fourni par défaut sur la plupart des
  installations ; sous Linux, il peut s'agir d'un paquet séparé tel que
  `gimp-python` selon la distribution).

Vous pouvez vérifier que Python est actif dans GIMP via
_Filtres ▸ Python-Fu ▸ Console_.

### Installation automatique (recommandée)

Depuis le dossier du projet, lancez :

```bash
python3 install.py
```

Le script détecte automatiquement le dossier de plug-ins utilisateur de votre
version de GIMP, copie le plugin au bon endroit et rend le script principal
exécutable. Options utiles :

```bash
python3 install.py --force            # écrase une installation existante
python3 install.py --uninstall        # désinstalle
python3 install.py --plugins-dir DIR  # cible un dossier plug-ins précis
python3 install.py --gimp-version 3.2 # force la version de configuration ciblée
```

Après l'installation, **redémarrez GIMP**.

### Installation manuelle

GIMP 3 exige qu'un plugin Python réside dans un dossier **portant le même nom**
que son script principal. Copiez donc l'ensemble du projet dans un dossier
`watermark_exporter/` à l'intérieur du dossier `plug-ins` de GIMP, de sorte à
obtenir :

```
<dossier plug-ins GIMP>/watermark_exporter/
    watermark_exporter.py     ← doit être exécutable (chmod +x sous Linux/macOS)
    lib/
    resources/
```

#### Linux

Dossier utilisateur typique :

```
~/.config/GIMP/3.2/plug-ins/
```

```bash
DEST=~/.config/GIMP/3.2/plug-ins/watermark_exporter
mkdir -p "$DEST"
cp -r watermark_exporter.py lib resources "$DEST"/
chmod +x "$DEST/watermark_exporter.py"
```

> Le chemin exact est indiqué par _Édition ▸ Préférences ▸ Dossiers ▸
> Greffons_. Selon la version, le dossier peut être `3.0` au lieu de `3.2`.

#### Windows

Dossier utilisateur typique :

```
%APPDATA%\GIMP\3.2\plug-ins\
```

1. Ouvrez l'explorateur et saisissez `%APPDATA%\GIMP\3.2\plug-ins` dans la barre
   d'adresse (créez le dossier `plug-ins` s'il n'existe pas).
2. Copiez-y le dossier `watermark_exporter` (contenant `watermark_exporter.py`,
   `lib`, `resources`).
3. Redémarrez GIMP. (Le bit exécutable n'est pas nécessaire sous Windows.)

Vous pouvez aussi lancer `python install.py` si Python est installé sur le
système.

#### macOS

Dossier utilisateur typique :

```
~/Library/Application Support/GIMP/3.2/plug-ins/
```

```bash
DEST=~/Library/Application\ Support/GIMP/3.2/plug-ins/watermark_exporter
mkdir -p "$DEST"
cp -r watermark_exporter.py lib resources "$DEST"/
chmod +x "$DEST/watermark_exporter.py"
```

> Le chemin exact est indiqué par _GIMP ▸ Préférences ▸ Dossiers ▸ Greffons_.

---

## Utilisation

1. Ouvrez dans GIMP toutes les images à traiter (_Fichier ▸ Ouvrir_).
2. Lancez **_Fichier ▸ Exporter toutes les images avec filigrane…_**.
3. Onglet **Filigrane** :
   - choisissez **Image** (sélectionnez un logo PNG) ou **Texte** (saisissez le
     texte, la police, la couleur, le contour, l'ombre) ;
4. Onglet **Export** :
   - réglez **opacité, taille, rotation, position, marges** ;
   - choisissez le **format** (PNG / JPEG / WebP) et la **qualité** ;
   - choisissez le **dossier de sortie** (ou « à côté de chaque original ») et
     l'option de sous-dossier `exports` ;
   - définissez la règle de **nommage** (préfixe, suffixe, date, motif) ;
   - ajustez au besoin la section **Charge machine** (voir ci-dessous) ;
5. Cliquez sur **Exporter**. La progression s'affiche et un résumé indique les
   éventuelles erreurs. Vos réglages sont mémorisés pour la prochaine fois.
   Pendant le traitement, **Annuler** interrompt le lot après l'image en cours.

### Charge machine

Un lot de grandes images sature facilement le processeur : le moteur de GIMP
(GEGL) parallélise sur tous les cœurs disponibles. Deux réglages, dans l'onglet
**Export**, permettent de rendre la main au système :

| Réglage                     | Défaut  | Effet                                                                 |
|-----------------------------|---------|-----------------------------------------------------------------------|
| **Brider le traitement**    | activé  | Limite le nombre de threads GEGL le temps de l'export.                |
| **Cœurs laissés libres**    | 1       | Nombre de cœurs réservés au reste du système (au moins 1 thread reste attribué à l'export). |
| **Pause entre images (ms)** | 50      | Temps rendu au système entre deux images d'un lot.                    |

La configuration d'origine de GEGL est restaurée à la fin du lot, même en cas
d'annulation ou d'erreur.

Sur un export **PNG**, le levier le plus efficace sur la durée reste le niveau
de **compression** (onglet Export) : le PNG étant sans perte, descendre de 9 à 3
réduit nettement le temps d'écriture pour quelques pour-cent de taille en plus.

### Variables de nommage

Dans le mode **Personnalisé**, le motif accepte les variables suivantes :

| Variable      | Signification                        | Exemple        |
|---------------|--------------------------------------|----------------|
| `{filename}`  | Nom de l'image d'origine (sans ext.) | `photo`        |
| `{date}`      | Date du jour (`AAAA-MM-JJ`)          | `2026-08-01`   |
| `{width}`     | Largeur exportée en pixels           | `640`          |
| `{height}`    | Hauteur exportée en pixels           | `480`          |
| `{prefix}`    | Préfixe saisi                        | `wm_`          |
| `{suffix}`    | Suffixe saisi                        | `_watermark`   |

Exemple : `{filename}_{width}x{height}` → `photo_640x480.png`.

---

## Dépannage

| Symptôme                                            | Cause probable / solution                                                                 |
|-----------------------------------------------------|-------------------------------------------------------------------------------------------|
| L'entrée de menu n'apparaît pas                     | Le dossier doit s'appeler `watermark_exporter` et contenir `watermark_exporter.py`. Sous Linux/macOS, le script doit être **exécutable**. Redémarrez GIMP. |
| « No module named lib »                             | Le dossier `lib/` n'a pas été copié à côté de `watermark_exporter.py`.                     |
| Le menu est grisé                                   | Ouvrez au moins une image : le plugin s'active dès qu'une image est présente.              |
| Le filigrane texte utilise une autre police         | Le nom de police saisi est introuvable dans GIMP ; la police courante est utilisée. Vérifiez le nom exact dans _Fenêtres ▸ Fenêtres ancrables ▸ Polices_. |
| L'ombre du texte n'est pas floutée                  | L'opération GEGL de flou est indisponible dans votre build ; l'ombre reste nette (comportement dégradé volontaire). |
| Rien ne s'exporte                                   | Vérifiez le dossier de sortie et les droits d'écriture ; consultez le journal (voir ci-dessous). |
| « Le script ne répond pas » pendant un long export  | L'interface reste vivante depuis la version non publiée (export découpé image par image). Si le message persiste, augmentez la **pause entre images** et vérifiez que le **bridage** est activé (section _Charge machine_). |
| L'export mobilise toute la machine                  | Section _Charge machine_ : augmentez les **cœurs laissés libres** et la **pause entre images**. Sur un lot PNG, baissez aussi la **compression**. |
| Où sont les journaux ?                              | Dans `<dossier GIMP>/watermark-exporter/watermark-exporter.log`. Activez le **mode debug** dans l'onglet Export pour plus de détails. |

Le **dossier GIMP** est indiqué par la console Python-Fu :

```python
from gi.repository import Gimp
print(Gimp.directory())
```

---

## FAQ

**Mes images originales sont-elles modifiées ?**
Non, jamais. Chaque image est dupliquée en mémoire ; le filigrane et l'export
sont appliqués à la copie, qui est ensuite détruite.

**Puis-je conserver la transparence ?**
Oui. Aux formats PNG et WebP, le canal alpha est préservé. Le format JPEG, qui
ne gère pas la transparence, est automatiquement aplati.

**Puis-je ajouter d'autres formats d'export ?**
Oui. Ajoutez une valeur à `ExportFormat` (`lib/constants.py`) et une petite
sous-classe de `BaseFormatExporter` enregistrée dans `EXPORTER_REGISTRY`
(`lib/exporter.py`). Aucune autre modification n'est nécessaire.

**Le plugin fonctionne-t-il en ligne de commande (batch) ?**
Oui. En mode non interactif, il réutilise les dernières préférences
enregistrées et traite toutes les images ouvertes sans afficher d'interface.

**Pourquoi GTK 3 alors que vous parlez d'interface moderne ?**
Parce que GIMP 3.2 est lui-même en GTK 3 (voir la note technique plus haut).
Utiliser GTK 4 rendrait le plugin non fonctionnel.

---

## Développement

### Structure du projet

```
watermark_exporter.py     Point d'entrée : enregistrement de la procédure GIMP.
install.py                Installateur multiplateforme.
lib/
    constants.py          Constantes et énumérations (sans dépendance GIMP).
    utils.py              Fonctions pures : géométrie, noms, validation.
    settings.py           Modèle de préférences + persistance JSON.
    logger.py             Configuration de la journalisation.
    watermark.py          Rendu du filigrane (image/texte) — API GIMP.
    exporter.py           Moteur d'export par lot + registre de formats.
    perf.py               Bridage réversible de la charge machine (GEGL).
    ui.py                 Interface GTK 3 (GimpUi).
resources/icon.svg        Icône du plugin.
tests/                    Tests unitaires (logique pure) + test de fumée GIMP.
locale/                   Emplacement des futurs catalogues de traduction.
```

### Lancer les tests

Les tests unitaires ne nécessitent **pas** GIMP (ils ne couvrent que la logique
pure) :

```bash
python3 -m unittest discover -s tests -v
# ou, si pytest est installé :
python3 -m pytest tests -v
```

Le **test de fumée** (`tests/smoke_gimp.py`) vérifie ce qui n'a de sens que face
au vrai runtime : pipeline complet, procédures d'export natives, effet réel du
réglage de compression, bridage GEGL et annulation en cours de lot. Il s'exécute
dans GIMP, sans interface :

```bash
gimp -i -s --batch-interpreter python-fu-eval \
     -b "exec(open('$PWD/tests/smoke_gimp.py').read())" --quit
```

`--quit` est indispensable : sans lui, GIMP reste en vie après les commandes
batch. Le code de retour n'étant pas propagé par GIMP, le script écrit son
verdict (`0` ou `1`) dans le fichier désigné par `SMOKE_VERDICT_FILE`.

### Vérifier la syntaxe et les imports

```bash
python3 -m py_compile watermark_exporter.py lib/*.py
```

### Conventions

- **PEP 8**, annotations de type (**typing**), **docstrings** systématiques.
- Architecture **SOLID**, responsabilité unique par module, aucune duplication.
- Les modules `constants`, `utils`, `settings` et `logger` restent **exempts de
  toute dépendance à GIMP** afin d'être testables sans lancer l'application.

---

## Architecture

Le flux principal est volontairement linéaire et découplé :

```
watermark_exporter.py
        │  (enregistre la procédure, charge les préférences, ouvre l'UI)
        ▼
lib/ui.py  ──(injecte un « export runner »)──►  lib/exporter.BatchExporter
                                                        │
                                 pour chaque image ouverte :
                                                        │
                    image.duplicate() ──► lib/watermark.WatermarkRenderer.apply()
                                                        │
                             fusion/aplatissement ──► BaseFormatExporter.export()
                                                        │
                                              ExportResult (succès/erreur)
```

Points clés de conception :

- **Inversion de dépendance** : l'interface ne connaît pas le moteur d'export ;
  elle reçoit un *callable* (`export_runner`). Cela facilite les tests et un
  éventuel remplacement de l'interface.
- **Ouvert/fermé** : les formats d'export sont des objets enregistrés dans un
  registre ; en ajouter un ne modifie aucun code existant.
- **Robustesse** : chaque image est traitée dans un bloc protégé ; une erreur
  isolée n'interrompt jamais le lot et est rapportée à l'utilisateur.

---

## Contribution

Les contributions sont les bienvenues !

1. Ouvrez une *issue* pour discuter d'un correctif ou d'une évolution.
2. Créez une branche dédiée.
3. Respectez les conventions (PEP 8, typing, docstrings) et **ajoutez des tests**
   pour toute nouvelle logique pure.
4. Vérifiez que `python3 -m unittest discover -s tests` passe et que
   `python3 -m py_compile watermark_exporter.py lib/*.py` ne produit aucune
   erreur.
5. Décrivez clairement votre modification dans la *pull request* et mettez à
   jour le `CHANGELOG.md`.

---

## Licence

Ce projet est distribué sous licence **GNU General Public License v3.0 ou
ultérieure** (GPL-3.0-or-later), compatible avec l'écosystème des greffons
GIMP. Voir le fichier [`LICENSE`](LICENSE) pour le texte complet.
