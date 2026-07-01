# LinkedIn via Apify

Source id : `linkedin`

LinkedIn est interrogé via l'actor Apify `valig/linkedin-jobs-scraper`. La
source sert surtout à augmenter le rappel sur les offres récentes publiées sur
LinkedIn, tout en gardant les champs bruts dans `source_data` pour audit.

## Stratégie rapide

| Phase | Stratégie |
| --- | --- |
| Collecte | Actor Apify synchrone avec titre, localisation, fraîcheur, contrat, niveau et modalité. |
| Filtre local | Utilise contrat, lieu, remote/hybrid et niveau d'expérience LinkedIn. |
| Analyse LLM | Envoie un bloc compact : URL LinkedIn/apply, recruteur si présent, entreprise et faits structurés. |
| Limite API | LinkedIn/Apify utilise un seul plafond global `LINKEDIN_MAX_RESULTS`, maximum `50`; pas de mode sans limite. |
| Limite produit | Les offres `EASY_APPLY` peuvent ne pas exposer d'URL externe de candidature. |

## Configuration

| Variable | Rôle |
| --- | --- |
| `APIFY_TOKEN` | Token Apify. |
| `LINKEDIN_CONTRACT_TYPE` | Codes actor, par défaut `F` pour full-time. |
| `LINKEDIN_EXPERIENCE_LEVEL` | Codes actor, par défaut `2,3,4`; `4` est utilisé seulement en fallback après `2,3`. |
| `LINKEDIN_REMOTE` | Codes actor, par défaut `1,2,3`. |
| `LINKEDIN_DATE_POSTED` | Fraîcheur par défaut : `any`, `today`, `3days`, `week`, `month` ou token Apify `r86400`. `3days` est élargi à `r604800`, car l'actor ne déclare pas de filtre 3 jours. |
| `LINKEDIN_MAX_RESULTS` | Limite globale LinkedIn/Apify ; défaut `50`, maximum autorisé `50`. |

## Appels

| Appel | Auth | Usage |
| --- | --- | --- |
| `POST api.apify.com/v2/acts/valig~linkedin-jobs-scraper/run-sync-get-dataset-items` | `token` query param | Lance l'actor et récupère les items dataset. |

Paramètres importants :

| Paramètre | Origine SmartApply |
| --- | --- |
| `title` | Requête rôle. |
| `location` | Localisation demandée. |
| `datePosted` | Conversion de `date_posted`, ex. `today -> r86400`. |
| `contractType` | `LINKEDIN_CONTRACT_TYPE` ou override. |
| `experienceLevel` | `LINKEDIN_EXPERIENCE_LEVEL` ou override. |
| `remote` | `LINKEDIN_REMOTE` ou override. |
| `limit` | `max_results`, sans multiplicateur de scan pour limiter l'usage Apify. |

Codes OpenAPI utiles :

| Champ | Codes envoyés |
| --- | --- |
| `contractType` | `F=Full-time`, `P=Part-time`, `C=Contract`, `T=Temporary`, `I=Internship`, `O=Other`. |
| `experienceLevel` | `1=Internship`, `2=Entry level`, `3=Associate`, `4=Mid-Senior level`, `5=Director`, `6=Executive`. |
| `remote` | `1=On-site`, `2=Remote`, `3=Hybrid`. |

Stratégie expérience : SmartApply appelle d'abord LinkedIn avec
`experienceLevel=["2", "3"]`. Si le nombre d'offres retournées est inférieur à
`max_results`, il lance un second appel avec `experienceLevel=["4"]` et
`skipJobId` pour éviter de revoir les offres déjà collectées.

## Mapping

| Sortie | Champs LinkedIn/Apify |
| --- | --- |
| `RawJob.title` | `title`. |
| `RawJob.company` | `companyName`. |
| `RawJob.location` | `location`. |
| `RawJob.contract_type` | `contractType`. |
| `RawJob.remote_policy` | `remote`, `workType` ou `location` si remote/hybrid est visible. |
| `RawJob.description` | `descriptionHtml` nettoyé, fallback `description`. |
| `RawJob.application_url` | `applyUrl`, fallback `url`. |
| `RawJob.published_date` | `postedDate`. |
| `source_data` | Payload Apify brut + `_smartapply_search`. |

## Stratégie filtre

Adapter : `build_linkedin_filter_facts`.

| Fact normalisé | Source | Effet |
| --- | --- | --- |
| `structured_contract_type` | `contractType` | Rejet stage, alternance, freelance, part-time, etc. si détecté. |
| `structured_location` | `location` | Rejet des lieux hors zone acceptée. |
| `structured_remote_policy` | `remote`, `workType`, `location` | Diagnostic remote/hybride. |
| `experience_requirement` | `experienceLevel` | Signal d'expérience pour audit et analyse locale. |

## Stratégie analyse

Builder : `build_linkedin_source_metadata`.

| Section | Contenu |
| --- | --- |
| `CONTACT_AND_APPLICATION_METADATA` | Source, entreprise, recruteur, type de candidature, URL offre/apply/company/recruiter. |
| `STRUCTURED_JOB_FACTS` | ID, titre, lieu, publication, candidatures, niveau, contrat, secteur, salaire et contexte de recherche. |
