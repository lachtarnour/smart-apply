# SmartApply AI

Pipeline d'optimisation de candidatures combinant scraping multi-sources (Google Jobs via SerpApi, France Travail, ingestion manuelle URL/texte), filtrage local, scoring sémantique, génération CV+email via LLM avec **validation anti-hallucination stricte**, recherche de contacts via Anymail Finder avec cache, et export d'emails prêts à envoyer (.eml ou brouillon Gmail).

> Le principe central : utiliser un LLM **uniquement là où il apporte une vraie valeur** (compréhension d'offre, adaptation rédactionnelle). Tout le reste — filtrage, scoring, dédoublonnage, validation — est local, déterministe, et gratuit. Résultat : un pipeline cohérent qui scale à des centaines d'offres pour quelques centimes d'API.

---

## Sommaire

1. [Architecture](#architecture)
2. [Structure des modules](#structure-des-modules)
3. [Installation rapide](#installation-rapide)
4. [Configuration `.env`](#configuration-env)
5. [Utilisation](#utilisation)
6. [Pipeline détaillé](#pipeline-détaillé)
7. [Anti-hallucination](#anti-hallucination)
8. [Tests](#tests)
9. [Coûts](#coûts)
10. [Limites & extensions](#limites--extensions)

---

## Architecture

```
Scraping (SerpApi / France Travail / Manuel)
        │
        ▼
   Parsing (clean + sections)
        │
        ▼
   Dédoublonnage (fuzzy multi-sources)
        │
        ▼
   Filtres locaux (règles, rapides, gratuits)
        │
        ▼
   Scoring sémantique (embeddings, top K)
        │
        ▼
   Analyse LLM structurée (top K offres)
        │
        ▼
   Sélection blocs CV (embeddings)
        │
        ▼
   Adaptation LLM du CV
        │
        ▼
   Validation anti-hallucination
        │           │
        ▼           ▼
  Export DOCX   Email .eml
        │           │
        ▼           ▼
   Stockage      Brouillon Gmail (optionnel)
        │
        ▼
   Dashboard Streamlit
```

Chaque flèche est un module indépendant et testable, branché via une interface (`Provider`, `Scraper`, `Generator`). On peut remplacer **n'importe quelle brique** sans toucher au reste.

---

## Structure des modules

| Module | Rôle | Fichiers clés |
|---|---|---|
| `smartapply.profile` | Profil candidat structuré, source de vérité | `schema.py`, `data/*.json`, `loader.py` |
| `smartapply.scrapers` | Collecte d'offres modulable | `base.py`, `serpapi.py`, `francetravail.py`, `manual.py`, `registry.py` |
| `smartapply.parsing` | Nettoyage + extraction de sections | `cleaner.py`, `sections.py` |
| `smartapply.dedup` | Dédoublonnage fuzzy multi-sources | `deduplicator.py` |
| `smartapply.filtering` | Filtres règles locaux | `rules.py`, `filters.py` |
| `smartapply.ranking` | Embeddings + scoring composite | `embeddings.py`, `scorer.py` |
| `smartapply.llm` | Provider LLM modulable + cache + usage | `provider.py`, `openai_provider.py`, `mock_provider.py`, `schemas.py`, `prompts/` |
| `smartapply.cv` | Sélection blocs → adaptation → validation → DOCX/PDF | `selector.py`, `adapter.py`, `validator.py`, `docx_generator.py` |
| `smartapply.email_agent` | Contact enrichi Anymail Finder + email template + .eml + Gmail draft | `template.py`, `contact_providers.py`, `eml_export.py`, `gmail_draft.py` |
| `smartapply.database` | Persistance SQLAlchemy | `models.py`, `session.py`, `repository.py` |
| `smartapply.pipeline` | Orchestrateur end-to-end | `pipeline.py` |
| `smartapply.app` | Dashboard Streamlit (5 pages) | `main.py`, `pages/` |
| `smartapply.cli` | CLI `smartapply ...` | `cli.py` |

---

## Installation rapide

**Prérequis** : Python 3.11 (recommandé) ou 3.12. Le projet est testé sur macOS arm64.

```bash
make install-all      # crée .venv, installe tout (UI, PDF, Gmail, dev)
cp .env.example .env  # renseigne OPENAI_API_KEY au minimum
make init-db          # crée la base SQLite
make test             # 218 tests, ~1 seconde
make run-app          # ouvre le dashboard Streamlit
```

Variante allégée si tu veux juste le cœur :

```bash
make install   # sans Streamlit / PDF / Gmail
```

---

## Configuration `.env`

Voir [`.env.example`](.env.example) pour la liste exhaustive. Les clés strictement nécessaires :

| Clé | Pour quoi | Obligatoire ? |
|---|---|---|
| `OPENAI_API_KEY` | Appels LLM et embeddings (par défaut) | Oui (sauf en mode mock) |
| `SERPAPI_API_KEY` | Collecte Google Jobs via SerpApi | Si tu actives `serpapi` |
| `FRANCETRAVAIL_CLIENT_ID` / `_SECRET` | API officielle France Travail | Si tu actives `francetravail` |
| `GMAIL_CREDENTIALS_PATH` | Brouillons Gmail (OAuth) | Si tu veux les brouillons |

Quelques réglages utiles :

```
SERPAPI_DATE_POSTED=week  # any, today, 3days, week, month
SERPAPI_MAX_PAGES=3       # 10 résultats max par page SerpApi
SERPAPI_UDS=              # filtre Google Jobs avancé, optionnel
```

`SERPAPI_DATE_POSTED=week` correspond au filtre Google Jobs “Last week”, donc aux offres des 7 derniers jours environ. SerpApi sert aussi un cache gratuit d'une heure quand la requête et les paramètres sont strictement identiques.

```
LLM_PROVIDER=openai            # openai | anthropic (futur) | mock
EMBEDDINGS_PROVIDER=openai     # openai | local | mock
JOB_SOURCES=serpapi,francetravail,manual
OPENAI_MODEL_CHEAP=gpt-4o-mini # pour analyse + quality gate
OPENAI_MODEL_SMART=gpt-4o      # pour génération CV + email en un appel
TOP_K_RANKED=25                # nb d'offres envoyées au LLM
TOP_K_CV_BLOCKS=8              # nb de blocs profil envoyés pour CV
```

---

## Utilisation

### CLI

```bash
# Pipeline complet sur SerpApi + France Travail
smartapply pipeline \
  --source serpapi --source francetravail \
  --query "Data Scientist" --location "Paris, France" \
  --date-posted week \
  --top-apply 5

# Étape par étape
smartapply ingest --source serpapi --query "ML Engineer" -l "Paris" --date-posted week
smartapply ingest-url --url https://acme.example/jobs/42
smartapply ingest-text --title "Data Scientist" --company "Acme" --file offer.txt
smartapply process --top-k 20
smartapply apply --job-id 42 --gmail-draft
smartapply autopilot \
  --query "Data Scientist OR Machine Learning Engineer" \
  --location "Paris, France" \
  --target-drafts 25 \
  --gmail-draft

# Suivi
smartapply list-jobs --status analyzed
smartapply list-applications
smartapply update-application --application-id 1 --status sent --notes "Relancer mardi"
smartapply stats
```

### Dashboard Streamlit

```bash
make run-app
```

5 pages :
- **Accueil** : KPIs + actions rapides (coller URL, coller texte, rechercher, traiter).
- **📋 Offres** : table triable + filtres par statut/source, détail + génération.
- **📝 Candidatures** : téléchargement DOCX/EML + bouton Gmail.
- **Suivi candidature** : statut, notes de relance et prochaine action.
- **🚀 Autopilot** : run quotidien haut volume, quality gate LLM, contacts enrichis, brouillons Gmail ou dossiers prêts formulaire.
- **👤 Profil** : visualisation du profil avec les `source_id` (utilisés par le validateur).
- **📊 Stats** : entonnoir, coût LLM par usage, historique.

### Python API

```python
from smartapply.pipeline import Pipeline

p = Pipeline()
p.ingest("serpapi", "Data Scientist", "Paris, France", max_results=30)
p.process_pending(top_k_analyze=20)
report = p.apply_to(
    job_id=42,
    contact_email="recrutement@example.com",  # optionnel
    create_gmail_draft=False,
)
print(report.docx_path, report.eml_path)
```

### Autopilot

L'autopilot vise un usage pratique : générer vite 20+ candidatures exploitables sans envoyer automatiquement à ta place.

```bash
smartapply autopilot \
  --source serpapi --source francetravail --source manual \
  --query "Data Scientist OR Machine Learning Engineer OR AI Engineer" \
  --location "Paris, France" \
  --target-drafts 25 \
  --gmail-draft
```

Comportement :
- offres avec contact fiable → CV + email + brouillon Gmail ;
- offres sans email mais avec formulaire → CV + email + `.eml`, statut `ready_for_form_submission`, URL du formulaire dans l'audit et les notes ;
- offres sans contact exploitable → CV + email + `.eml`, statut `ready_for_form_submission` ;
- candidatures trop faibles → statut `quality_rejected` avec audit.

Contacts :
- en mode manuel, aucun contact n'est cherché automatiquement : fournis `contact_email` si tu as déjà l'email recruteur/RH ;
- Anymail Finder cherche les contacts professionnels avec `ANYMAILFINDER_API_KEY` ;
- SerpApi sert à trouver des offres Google Jobs, pas à découvrir des contacts ;
- le LLM ne cherche pas les contacts par défaut : il reste utilisé pour analyse offre, adaptation CV, email et quality gate ;
- aucun email n'est généré par pattern générique : pas de `jobs@domain`, `recrutement@domain`, etc. inventés ;
- Anymail Finder cherche d'abord des emails d'entreprise génériques valides (`ANYMAILFINDER_COMPANY_EMAIL_TYPE=generic`) ;
- si un email générique recrutement/RH fiable existe (`jobs@`, `careers@`, `recrutement@`, `talent@`, `hr@`...), il devient le destinataire principal et le décideur n'est pas appelé ;
- sinon, SmartApply cherche un décideur (`ANYMAILFINDER_DECISION_MAKER_CATEGORIES=hr,engineering,it`) et garde les emails génériques faibles uniquement comme fallback ;
- seuls les emails `valid_email` / `valid_emails` sont utilisés, jamais les emails `risky` ;
- `ANYMAILFINDER_VERIFY_MANUAL_CONTACTS=true` peut vérifier les emails saisis manuellement via l'endpoint `verify-email` (0,2 crédit par vérification selon Anymail Finder) ;
- un cache par entreprise/domaine évite de consommer plusieurs crédits sur la même société, y compris quand aucun contact n'a été trouvé ;

---

## Pipeline détaillé

Économie d'API par cascade :

```
500 offres scrapées
→ 380 offres uniques après dédoublonnage          [LOCAL, gratuit]
→ 120 offres après filtres locaux                 [LOCAL, gratuit]
→  30 offres après scoring sémantique             [EMBEDDINGS, $0.0006]
→  20 analyses LLM courtes                        [LLM CHEAP, ~$0.02]
→   5 CV + emails personnalisés                   [LLM SMART, 1 appel/offre]
→   5 quality gates stricts                       [LLM CHEAP]
→   5 brouillons Gmail ou .eml prêts à envoyer    [LOCAL, gratuit]
```

| Étape | LLM | Justification |
|---|---|---|
| Scraping | Non | Extraction structurée |
| Nettoyage | Non | Regex + BeautifulSoup |
| Dédoublonnage | Non | RapidFuzz + Union-Find |
| Filtrage | Non | Règles dérivées du profil |
| Scoring | Embeddings | Cosinus, pas de génération |
| Analyse top K | **Oui (cheap)** | JSON structuré strict |
| CV + email | **Oui (smart)** | Un seul appel structuré par offre |
| Quality gate | Oui (cheap) | Validation stricte avant contact/draft |
| Contact RH | Non | Anymail Finder + cache, pas de LLM par défaut |
| Gmail draft | Non | API Gmail |

---

## Anti-hallucination

C'est le cœur du projet. Le LLM produit **toujours** une sortie structurée via `response_format=json_schema` strict (OpenAI). Chaque bullet du CV généré référence un `source_id` du profil. Le validateur (`smartapply.cv.validator.CvValidator`) vérifie ensuite :

**Erreurs (rejet automatique) :**
- `unknown_experience_id` / `unknown_bullet_id` / `unknown_project_id`
- `bullet_wrong_parent` : un bullet d'expérience A déclaré sous expérience B

**Warnings (conservés mais signalés) :**
- `hallucinated_number` : un nombre apparaît dans la sortie mais pas dans la source (les années sont tolérées)
- `low_text_overlap` : la sortie ne partage presque rien avec la source (rapidfuzz < 35)
- `bullet_too_long`, `summary_too_long` : dépassement des limites du style guide

En cas d'erreur, `CvValidator.auto_fix(cv)` enlève les éléments invalides — le CV est toujours produit, jamais avec du contenu inventé. Voir [`smartapply/cv/validator.py`](smartapply/cv/validator.py) et le test [`tests/test_cv.py`](tests/test_cv.py).

---

## Tests

```bash
make test       # 218 tests, ~1.2s, ne touche aucun service externe
```

Tous les appels HTTP et LLM sont mockés en tests. Pour les tests qui touchent vraiment OpenAI (rare et coûteux) :

```bash
LLM_PROVIDER=openai .venv/bin/pytest -m llm
```

Couverture par module :

| Module | Tests |
|---|---|
| profile | 20 |
| database | 6 |
| scrapers | 14 |
| parsing | 8 |
| dedup | 7 |
| filtering | 7 |
| ranking | 9 |
| llm | 11 |
| cv | 13 |
| email_agent | 9 |
| pipeline | 4 |
| autopilot | 3 |
| contact providers | 5 |
| integration end-to-end | 1 |

Le test d'intégration final ingère 5 offres réalistes, vérifie que le Sales Director et le Data Analyst BI sont rejetés, que les bons rôles sont rankés en tête, et que le CV produit contient bien les faits réels du profil (`0.67`, `Whisper`, `Emobot`, `PyTorch`).

---

## Coûts

Avec OpenAI (mai 2026) sur un cycle complet de 5 candidatures :

| Usage | Modèle | Tokens (in/out) | Coût |
|---|---|---|---|
| 30× embeddings | text-embedding-3-small | ~30K / 0 | < $0.001 |
| 20× analyse | gpt-4o-mini | ~30K / 5K | ~$0.008 |
| 5× CV + email | gpt-4o | ~30K / 9K | ~$0.17 |
| 5× quality gate | gpt-4o-mini | ~12K / 2K | ~$0.003 |
| **Total** | | | **~$0.18** |

Avec cache activé (`use_cache=True` par défaut), les ré-exécutions sont gratuites. Suivi en temps réel dans la page Stats du dashboard ou via `smartapply stats`.

---

## Limites & extensions

**Limites assumées :**
- SerpApi est un service payant (gratuit jusqu'à 250 recherches/mois).
- France Travail nécessite la création d'une app sur https://francetravail.io.
- Le mode manuel ne cherche pas d'email automatiquement : renseigne `contact_email` ou soumets via formulaire. L'autopilot utilise Anymail Finder + cache si configuré.
- Le générateur PDF utilise LibreOffice (`soffice --headless`) — pas embarqué. Le DOCX reste l'output primaire.
- Le validateur anti-hallucination ne couvre que les bullets : il fait confiance au prompt système pour le titre et le résumé. Les warnings restent visibles.

**Extensions naturelles :**
- Ajouter un nouveau scraper : implémenter `Scraper` et l'enregistrer dans `scrapers/registry.py`.
- Ajouter un nouveau LLM provider : implémenter `LLMProvider` et brancher dans la factory.
- Anthropic : la config (`anthropic_*`) et le squelette dans `provider.py` sont déjà en place.
- Embeddings locaux : `pip install -e '.[local-embeddings]'` puis `EMBEDDINGS_PROVIDER=local`.

---

## Sécurité

- Aucune clé API n'est commitée. `.env` est dans `.gitignore`. Le `.env.example` reste vide.
- Les credentials Gmail vont dans `secrets/` (gitignored).
- Les scrapers refusent les schémas non-HTTP (pas de `file://`).
- Les retries HTTP sont bornés (3 tentatives, backoff exponentiel via tenacity).
- Les tests forcent `OPENAI_API_KEY=""` et `SERPAPI_API_KEY=""` pour empêcher toute fuite vers une vraie API.

---

## Licence

MIT.
