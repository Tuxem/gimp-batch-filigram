# Journal des modifications

Toutes les évolutions notables de ce projet sont consignées dans ce fichier.

Le format s'inspire de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/)
et le projet suit le [versionnage sémantique](https://semver.org/lang/fr/).

## [Non publié]

### Corrigé

- **Fenêtre « ne répond pas » pendant les longs exports.** Le lot entier était
  traité à l'intérieur du gestionnaire de signal GTK : la boucle principale
  restait bloquée du début à la fin, et le gestionnaire de fenêtres déclarait
  la fenêtre morte (alors que l'export, lui, se terminait correctement). Le
  moteur expose désormais un **générateur** (`BatchExporter.iter_export`) que
  l'interface fait avancer image par image depuis la boucle GTK, et des
  **rappels d'étape** rendent la main au milieu d'une même image.
- **Réglages de compression PNG et de qualité JPEG/WebP silencieusement
  ignorés.** Le code appelait les procédures `file-*-save` de GIMP 2, absentes
  de GIMP 3 : chaque export retombait sur le repli `Gimp.file_save()`, avec les
  options par défaut. Les procédures `file-*-export` sont désormais utilisées,
  les anciens noms restant en secours.

### Ajouté

- **Annulation d'un export en cours** : le bouton « Annuler » (ou la fermeture
  de la fenêtre) interrompt le lot après l'image en cours, avec un résumé des
  images effectivement traitées.
- Section **« Charge machine »** dans l'onglet Export :
  - bridage du nombre de threads du moteur GEGL pendant l'export, pour laisser
    des cœurs libres au reste du système (activé par défaut, 1 cœur réservé) ;
  - **pause paramétrable entre deux images** (50 ms par défaut).
  La configuration GEGL d'origine est restaurée à la fin du lot, y compris en
  cas d'annulation ou d'erreur.
- **Test de fumée exécuté dans GIMP** (`tests/smoke_gimp.py`) : pipeline
  complet, procédures d'export natives, effet réel du réglage de compression,
  bridage GEGL et annulation en cours de lot.

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
