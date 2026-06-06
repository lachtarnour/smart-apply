# SerpAPI / Google Jobs

Source id : `serpapi`

SerpAPI interroge Google Jobs. C'est une source large et utile pour le rappel,
mais moins structurée que France Travail : les faits sont principalement issus
des champs Google Jobs et des `detected_extensions`.

## Stratégie rapide

| Phase | Stratégie |
| --- | --- |
| Collecte | Recherche Google Jobs avec localisation, langue, pays, chips et pagination. |
| Filtre local | Utilise les extensions détectées, le lieu et l'audit de recherche. |
| Analyse LLM | Pas de metadata builder dédié aujourd'hui ; l'analyse repose sur `RawJob`. |
| Limite | Google Jobs peut renvoyer peu ou zéro résultat avec des chips trop stricts. |

## Configuration

| Variable | Rôle |
| --- | --- |
| `SERPAPI_API_KEY` | Clé API SerpAPI. |
| `SERPAPI_GOOGLE_DOMAIN` | Domaine Google cible, ex. `google.com`. |
| `SERPAPI_HL`, `SERPAPI_GL` | Langue UI et pays. Pour la France, `hl=fr` est privilégié. |
| `SERPAPI_DEFAULT_LOCATION` | Localisation par défaut. |
| `SERPAPI_MAX_PAGES` | Nombre max de pages Google Jobs. |
| `SERPAPI_DATE_POSTED` | Fraîcheur : `any`, `today`, `3days`, `week`, `month`. |
| `SERPAPI_UDS` | Filtre Google Jobs brut optionnel. |

## Appels

| Appel | Auth | Usage |
| --- | --- | --- |
| `GET https://serpapi.com/search.json` | `api_key` | Recherche `engine=google_jobs`. |

Paramètres importants :

| Paramètre | Origine SmartApply |
| --- | --- |
| `q` | Requête rôle. |
| `location` | Localisation demandée ou défaut. |
| `google_domain`, `hl`, `gl` | Marché de recherche. |
| `chips` | Fraîcheur et filtres Google Jobs. |
| `next_page_token` | Pagination SerpAPI. |
| `uds` | Filtre brut optionnel. |

## Fallback recherche

| Cas | Fallback |
| --- | --- |
| Zéro résultat strict | Élargit `date_posted`, retire certains chips, puis tente `"{query} jobs in {location}"`. |
| Peu de résultats stricts | Élargit progressivement jusqu'à remplir environ une page cible. |
| Doublons multi-langue/pays | Dedup par `external_id`. |

Chaque offre garde `_smartapply_search` dans `source_data` pour auditer si elle
vient du strict ou d'un fallback.

## Mapping

| Sortie | Champs SerpAPI |
| --- | --- |
| `RawJob.title` | `title`. |
| `RawJob.company` | `company_name`. |
| `RawJob.location` | `location`. |
| `RawJob.contract_type` | `detected_extensions.schedule_type`. |
| `RawJob.remote_policy` | `detected_extensions.work_from_home` ou lieu contenant remote/hybrid. |
| `RawJob.description` | `description` + sections `job_highlights`. |
| `RawJob.application_url` | Premier `apply_options[].link`, fallback `share_link`. |
| `RawJob.apply_options` | Options de candidature Google Jobs. |
| `source_data` | Payload SerpAPI brut + `_smartapply_search`. |

## Stratégie filtre

Adapter : `build_serpapi_filter_facts`.

| Fact normalisé | Source | Effet |
| --- | --- | --- |
| `structured_contract_type` | `detected_extensions.schedule_type` | Rejet stage, alternance, freelance, part-time, prestataire si détecté. |
| `structured_location` | `location` | Rejet des lieux hors zone acceptée. |
| `structured_remote_policy` | `work_from_home` ou mots remote/hybrid dans `location` | Diagnostic remote/hybride. |
| `structured_search_origin/chips` | `_smartapply_search.result_origin/strict_chips` | Audit strict vs fallback. |

Principe : SerpAPI est traité conservativement. Si un fait structuré manque, le
filtre global retombe sur le titre, la description et les règles communes.

## Stratégie analyse

Il n'y a pas encore de `build_serpapi_source_metadata` enregistré dans
`smartapply.llm.source_metadata`.

Le LLM reçoit donc :

| Entrée analyzer | Contenu |
| --- | --- |
| `title`, `company`, `location` | Champs `RawJob`. |
| `application_url` | URL de candidature choisie. |
| `offer_body` | Description enrichie avec `job_highlights`. |
| `source` | `serpapi`. |
| `source_metadata` | Vide actuellement. |

Implication : les `apply_options`, le `search_origin` et les extensions SerpAPI
servent surtout au filtre/ranking/audit, sauf si elles ont été injectées dans
les champs `RawJob`.
