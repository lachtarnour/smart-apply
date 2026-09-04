# Élan

Élan est une application macOS native pour organiser une recherche d’emploi : collecte
multi-source, filtrage local, classement, analyse des offres, génération d’un CV et d’une
lettre adaptés, puis suivi manuel de chaque candidature.

## Fonctionnalités

- Recherche sur France Travail, Welcome to the Jungle, LinkedIn via Apify et Google Jobs via SerpApi.
- Ajout manuel d’une offre à partir de son contenu.
- Filtrage bilingue, dédoublonnage et classement selon le profil candidat.
- Analyse structurée des correspondances et des points à vérifier.
- Table d’offres triable avec sélection et actions groupées.
- Génération contrôlée du CV et de la lettre de motivation.
- Suivi des candidatures et accès direct à chaque dossier de documents.
- Interface Qt Quick pensée exclusivement pour macOS.

## Installation et lancement

Prérequis : macOS 13 ou version ultérieure et Python 3.11.

```bash
cp .env.example .env
make install-desktop
make init-db
make run-desktop
```

Construire et vérifier l’application autonome :

```bash
make build-macos
open dist/Elan.app
```

Le profil, la base SQLite, le cache et les dossiers de candidature restent dans
`~/Library/Application Support/Elan`. Un build ne remplace jamais un espace déjà initialisé.

## Configuration

Les réglages sont lus depuis `.env`.

| Variable | Usage | Obligatoire |
|---|---|---|
| `OPENAI_API_KEY` | Analyse, adaptation et embeddings | Oui, sauf provider `mock` |
| `FRANCETRAVAIL_CLIENT_ID` / `FRANCETRAVAIL_CLIENT_SECRET` | API France Travail | Si la source est active |
| `SERPAPI_API_KEY` | Google Jobs | Si la source est active |
| `APIFY_TOKEN` | LinkedIn Jobs | Si la source est active |
| `WTTJ_COOKIE` | Welcome to the Jungle | Si la source est active |
| `PROFILE_DIR` | Profil privé de référence | Optionnel |
| `DATABASE_URL` | Base SQLite locale | Optionnel |
| `OUTPUT_DIR` | Dossiers CV et lettres | Optionnel |
| `EMBEDDINGS_PROVIDER` | `openai`, `local` ou `mock` | Optionnel |

Le dossier `smartapply/profile/data/` est local et ignoré par Git. Le dossier versionné
`smartapply/profile/mock_profile/` documente uniquement la structure attendue.

## Architecture

```text
Sources d’offres
  → normalisation et dédoublonnage
  → filtrage local bilingue
  → classement sémantique
  → analyse structurée
  → génération CV + lettre
  → validation déterministe
  → suivi SQLite dans l’application macOS
```

Principaux modules :

- `smartapply/desktop` : application macOS et services d’interface.
- `smartapply/scrapers` : connecteurs vers les sources d’offres.
- `smartapply/offers` : normalisation des offres et métadonnées par source.
- `smartapply/filtering` : règles locales et signaux bilingues.
- `smartapply/ranking` : embeddings et scoring.
- `smartapply/llm` : analyses et génération structurées.
- `smartapply/cv` : adaptation, validation et rendu des documents.
- `smartapply/pipeline` : orchestration des différentes phases.
- `smartapply/database` : persistance SQLite locale.

## Qualité

```bash
make lint
make test-fast
make build-macos
```

Les sorties LLM sont validées par des schémas stricts. Le CV et la lettre sont contrôlés
contre le profil source avant leur enregistrement.

## CLI de maintenance

La CLI n’est pas une seconde interface produit ; elle sert au développement et au diagnostic.

```bash
elan --help
elan init-db
elan stats
```

## Licence

MIT
