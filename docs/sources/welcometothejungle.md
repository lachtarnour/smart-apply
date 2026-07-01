# Welcome to the Jungle

Source id : `welcometothejungle`

WTTJ lit le feed personnalisé `jobs-matches` du compte connecté. Les champs
`query` et `location` de `Scraper.search` ne filtrent pas côté WTTJ : ils sont
gardés dans `_smartapply_search` pour audit.

La fraîcheur de recherche est transmise au feed WTTJ avec `published_since` :
`today` → `last_24h`, `3days` → `last_3d`, `week` → `last_7d`. Pour `month`
(`30 derniers jours`) ou `any`, aucun paramètre de date n'est ajouté à l'URL.

## Stratégie rapide

| Phase | Stratégie |
| --- | --- |
| Collecte | Feed personnalisé authentifié, puis détail offre public/API. |
| Filtre local | Utilise surtout contrat, lieu, remote, expérience et provenance de recherche. |
| Analyse LLM | Envoie un bloc compact de métadonnées WTTJ, pas le JSON brut. |
| Limite | Les pages publiques peuvent renvoyer un `202` vide ; fallback API détail. |

## Configuration

| Variable | Rôle |
| --- | --- |
| `WTTJ_COOKIE` | Cookie d'une session WTTJ connectée. |
| `WTTJ_MAX_PAGES` | Cap de sécurité configurable pour la pagination WTTJ ; défaut `150`. |
| `WTTJ_PAGES`, `WTTJ_PER_PAGE` | Pagination demandée du feed matches ; défaut `150` pages et `50` offres/page, avec arrêt plus tôt si l'API annonce moins de pages. |
| `WTTJ_INCLUDE_COMPANY_PROFILE` | Enrichit avec la page entreprise WTTJ. |
| `WTTJ_SKIP_FAILED_JOBS` | Ignore une offre retirée/non parsable. |
| `WTTJ_ANALYZER_METADATA_FIELDS` | Champs transmis au LLM. |

```env
JOB_SOURCES=serpapi,francetravail,linkedin,welcometothejungle,manual
WTTJ_COOKIE=...
```

## Appels

| Appel | Auth | Usage |
| --- | --- | --- |
| `GET /api/v3/search/jobs?page=&per_page=` | Cookie WTTJ | Liste des matches personnalisés et slugs offre/entreprise. |
| `GET /api/v3/organizations/{company}/jobs/{job}` | Aucune | Détail JSON fiable quand le HTML public est vide. |
| `GET /fr/companies/{company}/jobs/{job}` | Aucune | JSON-LD `JobPosting`, description, metadata visibles. |
| `GET /fr/companies/{company}` | Aucune | Site officiel, domaine, présentation, secteurs, bureaux. |

## Mapping

| Sortie | Sources WTTJ principales |
| --- | --- |
| `RawJob.title/company/location` | JSON-LD offre ou API détail. |
| `RawJob.description` | Description + profil recherché + missions + process. |
| `RawJob.contract_type` | Page offre/API détail ; `full_time` reste `Full-time`, pas `CDI`. |
| `RawJob.remote_policy` | `matches_api.remote`, `remote_text`, API détail. |
| `RawJob.experience` | `experience_level`. |
| `RawJob.application_url` | URL canonique WTTJ. |
| `source_data.matches_api` | Données du feed personnalisé. |
| `source_data.detail_api` | Données API détail offre. |
| `source_data.company_profile` | Page entreprise si accessible. |
| `source_data.company_website/domain` | Site officiel et domaine pour contact/analyse. |
| `source_data.skills/workplace/salary` | Faits métier utiles au filtre et au LLM. |

## Stratégie filtre

Adapter : `build_wttj_filter_facts`.

| Fact normalisé | Source | Effet |
| --- | --- | --- |
| `experience_min_years` | `experience_level` | Rejet si l'expérience minimum dépasse la politique candidat. |
| `structured_contract_type` | `matches_api.contract_type`, fallback `employment_type` | Rejet stage, alternance, freelance, temps partiel, etc. |
| `structured_location` | `workplace`, fallback `matches_api.office` | Rejet des lieux hors zone acceptée. |
| `structured_remote_policy` | `matches_api.remote`, fallback `remote_text` | Diagnostic remote/hybride/onsite. |
| `structured_search_origin/chips` | `_smartapply_search` | Audit du feed et de la pagination. |

Principe : le filtre reste conservateur. Exemple : `full_time` indique un temps
plein, pas automatiquement un `CDI`.

## Stratégie analyse

Builder : `build_wttj_source_metadata`.

Le LLM reçoit deux sections courtes :

| Section | Contenu |
| --- | --- |
| `CONTACT_AND_APPLICATION_METADATA` | Source, domaine entreprise, URL profil, site officiel. |
| `STRUCTURED_JOB_FACTS` | Contrat, remote, date, expérience, salaire, lieu, skills, secteurs, présentation. |

Les champs sont pilotables avec `WTTJ_ANALYZER_METADATA_FIELDS`. Le prompt les
traite comme des ancres fiables supplémentaires : utiles pour la motivation,
les contacts et le contexte entreprise, mais jamais pour inventer des faits.
