# Démo vidéo Élan

La vidéo finale est dans `output/demo/Elan-demo.mp4` (1080p, environ 52 secondes).
Elle présente l’application native sans aucune piste audio, avec des encadrés
en points courts, des zones surlignées et un curseur animé.
La copie `output/demo/Elan-demo-sans-audio.mp4` contient cette même version muette.
Elle se termine sur la lettre générée, sans écran de conclusion.
Aucun bouton de visite guidée n’est ajouté à l’application.

## Le scénario

1. Accueil : deux offres sont déjà présentes dans la base dédiée.
2. Recherche : récupération de trois annonces dans un connecteur de démonstration.
3. Doublons : deux de ces annonces correspondent aux deux offres déjà présentes.
   Le vrai moteur de rapprochement les détecte et les affiche côte à côte.
4. Gestion : confirmation de chaque doublon par le bouton « Même offre ».
   La vidéo explique également le bouton « Offres différentes ».
5. Offres : trois offres distinctes restent disponibles. Analyse de l’offre
   Data Scientist NLP chez Aurore Labs, puis création de sa candidature.
6. Ouverture et présentation du CV et de la lettre PDF effectivement générés.

Le profil de Camille Martin, les entreprises, les offres et les réponses IA sont
fictifs. Les réponses sont déterministes et limitées au scénario Aurore Labs.
La collecte réseau et les appels IA sont simulés. La persistance, le filtrage,
la détection et la résolution des doublons, la validation et les rendus DOCX,
HTML et PDF utilisent les services réels de l’application. Les annotations
sont uniquement ajoutées au montage. Les clics sur CV et Lettre sont exécutés ;
leur ouverture système est interceptée pendant la capture, puis les PDF réels
sont affichés dans le montage.

## Base isolée

Tous les chemins sont forcés avant l’import de l’application. Aucune lecture
du `.env` de production, aucun identifiant externe et aucune écriture dans la
base personnelle ne sont nécessaires.

| Fichier dans `data/demo/` | État |
| --- | --- |
| `start.db` | 2 offres connues, aucun doublon |
| `after-fetch.db` | 5 annonces stockées, 2 doublons à vérifier |
| `after-duplicates.db` | 3 offres distinctes et 2 alias conservés |
| `demo.db` | État final : 1 candidature prête, CV et lettre générés |
| `audit.json` | Décisions, fichiers générés et événements d’ouverture |

Les documents sont dans `data/demo/documents/1/`, le profil dans
`data/demo/profile/`. Les captures sont dans `data/demo/captures/`.
Les dossiers `data/` et `output/` sont déjà exclus de Git.

## Rejouer

Depuis la racine du projet, avec l’environnement Python desktop installé :

```sh
# Recréer uniquement la base marquée comme base de démonstration et recapturer.
.venv/bin/python tools/demo/capture.py --reset

# Ouvrir l’état final de la démo dans l’application native.
.venv/bin/python tools/demo/capture.py --interactive

# Ou démarrer une démo interactive depuis les deux offres initiales.
.venv/bin/python tools/demo/capture.py --reset --interactive
```

Le mode interactif utilise lui aussi la base de démo. La génération préparée
concerne uniquement le poste Data Scientist NLP chez Aurore Labs.
`--reset` refuse tout dossier non marqué comme appartenant à cette démo.
La capture nécessite Chrome/Chromium ou WeasyPrint fonctionnel pour les PDF.

## Refaire le montage

Les commandes ci-dessous recréent le montage narré historique. Pour obtenir
la version finale muette, supprimer ensuite toutes les pistes audio, sans
réencoder l’image :

```sh
ffmpeg -i output/demo/Elan-demo.mp4 -map 0:v:0 -c:v copy -an -movflags +faststart output/demo/Elan-demo-sans-audio.mp4
```

```sh
.venv/bin/pip install --target data/demo-video-deps Pillow PyMuPDF imageio-ffmpeg edge-tts
PYTHONPATH="$PWD/data/demo-video-deps" .venv/bin/python tools/demo/narration.py
PYTHONPATH="$PWD/data/demo-video-deps" .venv/bin/python tools/demo/render.py --audio-dir output/demo/narration-claire
```

La narration utilise maintenant la voix française **Denise Neural**, avec son
débit naturel (`+0%`), via le service vocal Microsoft Edge. Seules les 14 phrases
de narration sont transmises : la base et le profil restent locaux. Le script
`narration.py` ne lit aucun identifiant et conserve les clips en cache ; ses
options `--voice` et `--rate` permettent d’ajuster le locuteur et le rythme.
Le service et ses paramètres sont utilisés via [edge-tts](https://github.com/rany2/edge-tts).

Le montage utilise les clips WAV locaux, raccourcit les silences excessifs et
normalise le volume de la voix, sans accélérer la parole.
Chrome doit pouvoir s’exécuter pour la création initiale des PDF. Les anciennes
voix macOS restent disponibles dans `render.py` sans `--audio-dir`, mais ne
servent pas à la version avec la voix Denise.

`render.py --preview-only` produit les images de contrôle sans encoder la vidéo.
Les textes, le rythme et les zones sélectionnées se modifient dans `SCENES`
de `render.py`. Le dossier `output/demo/` contient aussi l’affiche, la chronologie
et les sous-titres français au format SRT. `montage/` contient les intermédiaires.

## Vérifications effectuées

- Recherche : exactement 3 annonces récupérées, 2 doublons en attente.
- Résolution : 2 alias confirmés, aucune décision en attente, 3 offres distinctes.
- Génération : candidature au statut `ready_for_form_submission`, aucun avertissement.
- CV et lettre : un PDF d’une page chacun, texte extrait et rendu inspecté.
- Boutons CV et Lettre : ouverture de chacun des fichiers attendus vérifiée.
- SQLite : contrôle d’intégrité réussi pour les quatre états.
- MP4 final : décodage complet réussi ; 1920 × 1080, 24 images/s, 51,5 secondes ; aucune piste audio.
