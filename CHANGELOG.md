# Journal des modifications

Toutes les évolutions notables de ce projet sont consignées dans ce fichier.

Le format s'inspire de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/)
et le projet suit le [versionnage sémantique](https://semver.org/lang/fr/).

## [1.0.0] — 2026-07-31

### Ajouté

- Première version publique.
- Export par lot de **toutes les images ouvertes** dans GIMP 3.2.x, en une
  seule opération, sans jamais modifier les originaux (traitement sur copie
  temporaire).
- Filigrane en deux modes :
  - **Image** : logo PNG transparent, redimensionné en conservant le ratio,
    opacité configurable.
  - **Texte** : police, taille, couleur, opacité, **contour** et **ombre
    portée** floutée.
- **Neuf positions** classiques + **coordonnées X/Y personnalisées**.
- Trois **modes de taille** : pourcentage de la largeur, pourcentage de la
  hauteur, taille fixe (px).
- **Marges** paramétrables en pixels ou en pourcentage.
- **Rotation** du filigrane (angle libre, positif ou négatif).
- **Opacité** globale de 0 à 100 %.
- Export **PNG**, **JPEG** et **WebP**, via une architecture extensible
  (registre d'exporteurs) permettant d'ajouter facilement d'autres formats.
- **Nommage** des fichiers : identique, préfixe, suffixe, date, ou motif
  personnalisé avec variables `{filename}`, `{date}`, `{width}`, `{height}`,
  `{prefix}`, `{suffix}`.
- Choix du **dossier de sortie** (ou export à côté de chaque image d'origine),
  avec création automatique optionnelle d'un sous-dossier `exports`.
- **Préférences persistantes** (JSON) : dernier logo, dernier dossier, opacité,
  taille, format, position, etc.
- **Barre de progression** non bloquante et **journal des résultats** dans
  l'interface.
- **Journalisation** complète (niveaux INFO / WARNING / ERROR / DEBUG) avec
  fichier tournant et **mode debug** activable.
- Gestion d'erreurs robuste : logo absent, dossier inaccessible, fichier
  verrouillé, format indisponible, image invalide… le plugin ne plante jamais
  et rapporte les échecs image par image.
- Interface **GTK 3** moderne (onglets Filigrane / Export) via `GimpUi`.
- Installateur multiplateforme (`install.py`) avec détection automatique du
  dossier de plug-ins (Linux, Windows, macOS).
- Suite de **tests unitaires** (géométrie, positions, nommage, préférences,
  validation).

### Notes techniques

- GIMP 3.2.x étant une application **GTK 3**, l'interface du plugin utilise
  GTK 3 (et non GTK 4, incompatible dans le même processus). Voir le `README`
  pour le détail.
