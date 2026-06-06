# SmartApply

Outil d'assistance pour candidater plus vite et plus juste. SmartApply collecte des offres
sur plusieurs sources, filtre localement le bruit, classe les meilleures par pertinence,
analyse les retenues avec un LLM, adapte ton CV + lettre + email à chaque offre, et prépare
un brouillon Gmail prêt à envoyer. **Rien ne part automatiquement** — chaque étape passe
par ta validation.

## Principes

- **Cascade de coûts** — tout ce qui est déterministe (parsing, dédoublonnage, filtre, scoring) reste local et gratuit ; le LLM n'intervient que là où il apporte vraiment de la valeur (compréhension d'offre, rédaction CV/lettre/email).
- **Anti-hallucination strict** — chaque bullet du CV pointe vers un `source_id` du profil et passe un validateur déterministe qui élimine les faits inventés.
- **Contrôle à chaque étape** — l'UI Streamlit expose 5 étapes manuelles (Fetch → Scoring → Analyse → Génération → Finalisation), tu peux désélectionner, surcharger un filtre ou récupérer une offre archivée à tout moment.
- **Aucun envoi automatique** — la brique Gmail crée uniquement un brouillon (scope `gmail.compose`), un test statique AST en CI bloque tout ajout d'appel `send`.

## Démarrage rapide

```bash
make install-all      # crée .venv, installe UI + PDF + Gmail + dev
cp .env.example .env  # renseigne au minimum OPENAI_API_KEY
make init-db
make test             # 578 tests, ~6 secondes, 100 % offline
make run-app          # ouvre le dashboard Streamlit
```

Variante allégée sans Streamlit / PDF / Gmail : `make install`.

## Ce que SmartApply gère pour toi

- **Vraies nouvelles offres au fetch** — `max_results=N` cible désormais N offres *vraiment nouvelles* (déjà absentes de ta DB), pas N offres brutes dont la moitié sont des doublons.
- **Localisations FR résolues automatiquement** — `Paris` → `departement=75`, `Île-de-France` → `region=11`, top villes pinnées offline, fallback API `geo.api.gouv.fr` pour les 34 945 communes (cache disque versionné).
- **Champ expérience structuré sur France Travail** — `experienceExige` / `experienceLibelle` extraits et exposés au filtre + au prompt LLM, plus besoin de parser la description.
- **Filtre local prudent** — refactorisé en signaux typés (`contract_signals`, `location_signals`, `role_signals`, `seniority`) ; corrections P0 contre les faux rejets (`apprentissage automatique` ≠ contrat d'apprentissage, `institution indépendante` ≠ travailleur indépendant, `30 ans d'expérience` côté entreprise ≠ exigé du candidat, `rattaché au directeur` ≠ poste de management).
- **Récupération manuelle d'une offre archivée** — bouton "Réinjecter avec score maximal" sur la page Offres : remet l'offre en `SHORTLISTED` avec toutes les composantes à 1.0, audit conservé.
- **Slider Top-K interactif** — étape 2 du Workflow, ajustable par run, défaut depuis `settings.top_k_ranked`.
- **Aperçu Gmail avant création** — étape 5 affiche destinataire / objet / pièces jointes / taille encodée sans aucun appel réseau, puis tu décides de créer ou non le brouillon.
- **Classification des hosts de candidature** — `company_domain` / `ats` / `partner_job_board` / `application_redirect` / `unknown` pour orienter la stratégie email/formulaire sans inventer un domaine.
- **Validateur lettre de motivation** — 3 paragraphes obligatoires, alias autorisés sourcés du profil, élisions françaises normalisées, acronymes protégés (ML, IA, RAG).

## Workflow Streamlit

| # | Étape | Ce qui se passe | LLM ? |
|---|---|---|---|
| 1 | **Fetch** | Recherche multi-sources, filtre local, dédup contre la DB, override manuel possible | Non |
| 2 | **Scoring** | Embeddings + scoring composite, slider Top-K présélection pour l'analyse | Embeddings |
| 3 | **Analyse** | Extraction structurée (rôle, skills, risques, contact) | LLM cheap |
| 4 | **Génération** | CV + lettre + email adaptés à l'offre (un seul appel structuré) | LLM smart |
| 5 | **Finalisation** | Dry-run preview, puis création brouillon Gmail OU export `.eml` | Non |

## CLI

```bash
smartapply init-db
smartapply ingest --source francetravail --query "Data Scientist" -l "Paris" --date-posted week
smartapply ingest-url --url https://acme.example/jobs/42
smartapply ingest-text --title "ML Engineer" --company "Acme" --file offer.txt
smartapply process --top-k 20
smartapply apply --job-id 42 --gmail-draft
smartapply pipeline --source serpapi --source francetravail --query "Data Scientist" -l "Paris" --top-apply 5
smartapply autopilot --query "Data Scientist OR ML Engineer" -l "Paris, France" --target-drafts 25 --gmail-draft
smartapply gmail-check                # diagnostic config Gmail, aucun appel réseau
smartapply list-jobs --status analyzed
smartapply list-applications
smartapply update-application --application-id 1 --status sent --notes "Relancer mardi"
smartapply stats                       # coût LLM + entonnoir par statut
```

## Sources d'offres

| Source | Mode | Clé requise |
|---|---|---|
| **France Travail** | API officielle (CDI/CDD/MIS), expérience + localisation structurées | `FRANCETRAVAIL_CLIENT_ID` / `_SECRET` |
| **Google Jobs (SerpApi)** | API payante, couverture mondiale, filtre `date_posted` | `SERPAPI_API_KEY` |
| **Welcome to the Jungle** | Matches personnalisés via ta session, hydratation profil entreprise | `WTTJ_COOKIE` |
| **Manuel** | URL ou texte collé, refuse les schémas non-HTTP et les IPs privées | — |

Détails par source (paramètres, quirks, fallbacks) : [`docs/sources/`](docs/sources/).

## Configuration `.env`

| Clé | Pour quoi | Obligatoire ? |
|---|---|---|
| `OPENAI_API_KEY` | LLM + embeddings | Oui (sauf mode `mock`) |
| `SERPAPI_API_KEY` | Google Jobs via SerpApi | Si `serpapi` actif |
| `FRANCETRAVAIL_CLIENT_ID` / `_SECRET` | API France Travail | Si `francetravail` actif |
| `WTTJ_COOKIE` | Welcome to the Jungle | Si `welcometothejungle` actif |
| `GMAIL_CREDENTIALS_PATH` | Brouillons Gmail (OAuth Desktop client) | Si tu veux les brouillons |
| `ANYMAILFINDER_API_KEY` | Découverte de contacts RH | Si tu veux l'enrichissement contact |
| `OPENAI_MODEL_CHEAP` / `OPENAI_MODEL_SMART` | Override des modèles par défaut | Non |
| `TOP_K_RANKED` | Défaut du slider Top-K en étape 2 | Non (défaut 25) |
| `EMBEDDINGS_PROVIDER` | `openai` / `local` / `mock` | Non (défaut `openai`) |

Voir [`.env.example`](.env.example) pour la liste complète.

### Gmail : créer un brouillon (jamais d'envoi)

1. `make install-all` (ou `.venv/bin/pip install -e '.[gmail]'`)
2. Sur Google Cloud Console : activer Gmail API, créer un client OAuth **Desktop app**, télécharger le JSON, placer dans `secrets/credentials.json`.
3. `smartapply gmail-check` valide la config sans toucher au réseau.
4. Crée ton premier brouillon depuis l'UI (étape 5) ou via `smartapply apply --job-id N --gmail-draft`. Le navigateur s'ouvrira une seule fois pour l'OAuth, puis `secrets/token.json` sera réutilisé.

Seul endpoint Gmail appelé : `users().drafts().create`. Un test AST statique (`tests/test_email_agent.py::test_gmail_draft_module_has_no_send_calls`) bloque toute introduction de `send` / `messages.send` / `drafts.send`.

## Architecture

```
Scraping (SerpApi / France Travail / WTTJ / Manuel)
    │
    ▼
Parsing + dédoublonnage  ──────────────  LOCAL, gratuit
    │
    ▼
Filtre local par signaux typés (contract / location / role / seniority)
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

Modules : `scrapers`, `parsing`, `dedup`, `filtering` (avec `source_facts`), `ranking`, `llm` (avec `analyzer_input`, `source_metadata`), `cv`, `email_agent` (Gmail + .eml + contacts), `pipeline` (avec `reports`, `apply_specs`), `app` (Streamlit 5 pages), `cli`. Chacun branché via une interface (`Scraper`, `LLMProvider`, `EmbeddingsProvider`, `ContactProvider`) et remplaçable indépendamment.

## Anti-hallucination

Trois garde-fous combinés :

- **Schéma JSON strict** sur tous les appels LLM (`response_format=json_schema`), pas de texte libre.
- **Evidence gate dans le prompt d'analyse** — interdit d'utiliser le titre, la metadata scraper ou le slug d'URL comme preuve pour `required_skills`, `extracted_location`, `company_context`, `contact_domain_hint`. Pas de "Capgemini.com" inventé à partir du nom de l'entreprise.
- **Validateur CV/lettre** (`smartapply.cv.validator`, `smartapply.cv.motivation_validator`) — chaque bullet doit pointer vers un `source_id` du profil, les chiffres inventés sont signalés, `auto_fix` retire les éléments non valides, la lettre doit avoir 3 paragraphes.
- **Quality gate** — un dernier appel LLM cheap relit le dossier avant qu'il soit marqué prêt.

Détail : `smartapply/cv/validator.py`, `smartapply/cv/motivation_validator.py`, `smartapply/llm/prompts/job_analysis.py`, `tests/test_cv.py`.

## Coûts indicatifs (cycle de 5 candidatures)

| Usage | Modèle | Coût |
|---|---|---|
| Embeddings 30 offres | `text-embedding-3-small` | < $0.001 |
| Analyse 20 offres | `gpt-4o-mini` | ~$0.01 |
| CV + lettre + email × 5 | `gpt-4o` | ~$0.17 |
| Quality gate × 5 | `gpt-4o-mini` | ~$0.005 |
| **Total** | | **~$0.18** |

Cache LLM activé par défaut → ré-exécution gratuite. Suivi dans la page Stats du dashboard ou via `smartapply stats`.

## Tests

```bash
make test         # 578 tests, ~6 s, 100 % offline
make test-fast    # exclut le test d'intégration end-to-end
```

Toutes les API externes (SerpApi, France Travail, OpenAI, geo.api.gouv.fr, Gmail) sont mockées. Tests de contrat statique inclus : `test_pages_detail_dict_contract` (clés du dict UI), `test_gmail_draft_module_has_no_send_calls` (anti-envoi Gmail), `test_workflow_step5_uses_creer_brouillon_label_not_envoyer` (labels UI).

## Sécurité

- `.env`, `secrets/`, `data/secrets/`, `*token*.json`, `credentials.json`, `gmail_credentials.json` sont gitignored.
- `OPENAI_API_KEY` et `SERPAPI_API_KEY` forcés à vide pendant les tests.
- Le scraper manuel refuse les URLs non-HTTP, les hôtes locaux et les IPs privées (anti-SSRF).
- Retries HTTP bornés (3 tentatives, backoff exponentiel via `tenacity`).
- La brique Gmail ne logue ni destinataire, ni body, ni token : seulement `draft_id`, nb de pièces jointes et taille encodée.

## Limites connues

- France Travail ne couvre que la France (les autres pays passent par SerpApi).
- WTTJ exige une session valide ; pas d'OAuth, juste un cookie copié depuis le navigateur.
- Le résolveur de localisation cache 34 945 communes en mémoire (~3 MB) au premier run.
- L'autopilot ne soumet jamais un formulaire ATS — il génère le dossier et marque `ready_for_form_submission` ; tu soumets à la main.
- Anthropic en provider LLM est cadré côté config (`anthropic_*`) mais pas encore branché à 100 %.

## Étendre

- **Nouveau scraper** : implémenter `smartapply.scrapers.base.Scraper`, enregistrer dans `smartapply/scrapers/registry.py`, ajouter un builder dans `filtering/source_facts.py` et `llm/source_metadata.py`.
- **Nouveau LLM provider** : implémenter `LLMProvider` (voir `MockLLMProvider`), brancher dans la factory.
- **Embeddings locaux** : `pip install -e '.[local-embeddings]'`, puis `EMBEDDINGS_PROVIDER=local`.
- **Nouveau host pour la classification contact** : éditer le catalogue dans `smartapply/email_agent/contact_providers.py`, ajouter un test dans `tests/test_contact_providers.py`.

## Licence

MIT.
