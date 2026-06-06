# SmartApply

Outil d'assistance pour candidater plus vite et plus juste. SmartApply collecte des offres
sur plusieurs sources, filtre localement le bruit, classe les meilleures par pertinence,
analyse les retenues avec un LLM, adapte ton CV + lettre + email à chaque offre, et prépare
un brouillon Gmail prêt à envoyer. **Rien ne part automatiquement** — chaque étape passe
par ta validation.

## Principes

- **Cascade de coûts** — tout ce qui est déterministe (parsing, dédoublonnage, filtre, scoring) reste local et gratuit ; le LLM n'intervient que là où il apporte vraiment de la valeur (compréhension d'offre, rédaction CV/lettre/email).
- **Anti-hallucination strict** — chaque bullet du CV pointe vers un `source_id` du profil et passe un validateur qui élimine les faits inventés.
- **Contrôle à chaque étape** — l'UI Streamlit expose 5 étapes manuelles (Fetch → Scoring → Analyse → Génération → Finalisation), tu peux désélectionner ou récupérer une offre archivée à tout moment.
- **Aucun envoi automatique** — la brique Gmail crée uniquement un brouillon (scope `gmail.compose`), un test statique en CI bloque tout ajout d'appel `send`.

## Démarrage rapide

```bash
make install-all      # crée .venv, installe UI + PDF + Gmail + dev
cp .env.example .env  # renseigne au minimum OPENAI_API_KEY
make init-db
make test             # 578 tests, ~6 secondes, 100 % offline
make run-app          # ouvre le dashboard Streamlit
```

Variante allégée sans Streamlit / PDF / Gmail : `make install`.

## Workflow Streamlit

| # | Étape | Ce qui se passe | LLM ? |
|---|---|---|---|
| 1 | **Fetch** | Recherche multi-sources, filtre local par règles, dédup contre DB | Non |
| 2 | **Scoring** | Embeddings + scoring composite, slider Top-K présélection | Embeddings |
| 3 | **Analyse** | Extraction structurée (rôle, skills, risques, contact) | LLM cheap |
| 4 | **Génération** | CV + lettre + email adaptés en un appel | LLM smart |
| 5 | **Finalisation** | Dry-run preview, puis création brouillon Gmail OU export `.eml` | Non |

Une CLI équivalente existe : `smartapply ingest`, `process`, `apply`, `pipeline`, `autopilot`, `gmail-check`.

## Sources d'offres

| Source | Mode | Clé requise |
|---|---|---|
| **France Travail** | API officielle, structurée, FR uniquement | `FRANCETRAVAIL_CLIENT_ID` / `_SECRET` |
| **Google Jobs (SerpApi)** | API payante, couverture mondiale | `SERPAPI_API_KEY` |
| **Welcome to the Jungle** | Matches personnalisés via ta session | `WTTJ_COOKIE` |
| **Manuel** | URL ou texte collé | — |

Les ergonomies par source (localisation, expérience, contrats) sont documentées dans `docs/sources/`.

## Configuration `.env`

| Clé | Pour quoi | Obligatoire ? |
|---|---|---|
| `OPENAI_API_KEY` | LLM + embeddings | Oui (sauf mode `mock`) |
| `SERPAPI_API_KEY` | Google Jobs via SerpApi | Si tu actives `serpapi` |
| `FRANCETRAVAIL_CLIENT_ID` / `_SECRET` | API France Travail | Si tu actives `francetravail` |
| `WTTJ_COOKIE` | Welcome to the Jungle | Si tu actives `welcometothejungle` |
| `GMAIL_CREDENTIALS_PATH` | Brouillons Gmail | Si tu veux les brouillons Gmail |
| `ANYMAILFINDER_API_KEY` | Découverte de contacts RH | Si tu veux l'enrichissement contact |

Voir [`.env.example`](.env.example) pour la liste complète.

### Gmail : créer un brouillon (pas un envoi)

1. `make install-all` (ou `.venv/bin/pip install -e '.[gmail]'`)
2. Sur Google Cloud Console : activer Gmail API, créer un client OAuth **Desktop app**, télécharger le JSON, placer dans `secrets/credentials.json`.
3. `.venv/bin/python -m smartapply.cli gmail-check` valide la config sans toucher au réseau.
4. Crée ton premier brouillon depuis l'UI (étape 5) ou via `smartapply apply --job-id N --gmail-draft`.

Seul endpoint Gmail appelé : `users().drafts().create`. Un test statique AST (`tests/test_email_agent.py::test_gmail_draft_module_has_no_send_calls`) bloque toute introduction de `send` / `messages.send` / `drafts.send`.

## Architecture

```
Scraping (SerpApi / France Travail / WTTJ / Manuel)
    │
    ▼
Parsing + dédoublonnage  ──────────────  LOCAL, gratuit
    │
    ▼
Filtre local (signaux contrat / location / role / seniority)
    │
    ▼
Scoring sémantique (embeddings, Top-K configurable) ──── ~$0.001
    │
    ▼
Analyse LLM structurée (top-K offres) ───────────────── ~$0.01
    │
    ▼
Génération CV + lettre + email (un appel par offre) ── ~$0.03/offre
    │
    ▼
Validation anti-hallucination (déterministe)
    │
    ▼
Brouillon Gmail OU export `.eml` ─────── jamais d'envoi
    │
    ▼
DB SQLite + dashboard Streamlit
```

Modules principaux : `scrapers`, `parsing`, `dedup`, `filtering`, `ranking`, `llm`, `cv`, `email_agent`, `pipeline`, `app`, `cli`. Chacun est branché via une interface (`Scraper`, `LLMProvider`, `EmbeddingsProvider`, `ContactProvider`) et remplaçable indépendamment.

## Anti-hallucination

Trois garde-fous combinés :

- **Schéma JSON strict** sur tous les appels LLM (`response_format=json_schema`), pas de texte libre.
- **Validateur CV/lettre** (`smartapply.cv.validator`) : chaque bullet doit pointer vers un `source_id` du profil ; les chiffres inventés sont signalés ; `auto_fix` retire les éléments non valides.
- **Quality gate** : un dernier appel cheap relit le dossier avant de le marquer prêt à envoyer.

Détail : `smartapply/cv/validator.py`, `tests/test_cv.py`.

## Coûts indicatifs (un cycle de 5 candidatures)

| Usage | Modèle | Coût |
|---|---|---|
| Embeddings 30 offres | `text-embedding-3-small` | < $0.001 |
| Analyse 20 offres | `gpt-4o-mini` | ~$0.01 |
| CV + lettre + email × 5 | `gpt-4o` | ~$0.17 |
| Quality gate × 5 | `gpt-4o-mini` | ~$0.005 |
| **Total** | | **~$0.18** |

Le cache LLM est activé par défaut → ré-exécution gratuite. Suivi en temps réel dans la page Stats du dashboard ou via `smartapply stats`.

## Tests

```bash
make test         # 578 tests, ~6 s, 100 % offline
make test-fast    # exclut le test d'intégration end-to-end
```

Toutes les API externes (SerpApi, France Travail, OpenAI, geo.api.gouv.fr, Gmail) sont mockées en test. Aucune clé n'est requise pour faire tourner la suite.

## Sécurité

- `.env`, `secrets/`, `data/secrets/`, `*token*.json`, `credentials.json` sont gitignored.
- `OPENAI_API_KEY` et `SERPAPI_API_KEY` sont forcés à vide pendant les tests pour empêcher toute fuite.
- Le scraper manuel refuse les URLs non-HTTP, les hôtes locaux et les IPs privées.
- Les retries HTTP sont bornés (3 tentatives, backoff exponentiel).
- La création de brouillon Gmail ne logue ni le destinataire, ni le body, ni le token.

## Étendre

- **Nouveau scraper** : implémenter `smartapply.scrapers.base.Scraper`, enregistrer dans `smartapply/scrapers/registry.py`, ajouter un builder dans `filtering/source_facts.py` et `llm/source_metadata.py`.
- **Nouveau LLM provider** : implémenter `LLMProvider` (voir `MockLLMProvider`), brancher dans la factory.
- **Embeddings locaux** : `pip install -e '.[local-embeddings]'`, puis `EMBEDDINGS_PROVIDER=local`.

## Licence

MIT.
