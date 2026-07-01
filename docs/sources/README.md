# Sources de jobs

Ce dossier documente le contrat de chaque source externe sous forme compacte :

| Bloc | Question couverte |
| --- | --- |
| Stratégie rapide | Comment la source sert la collecte, le filtre et l'analyse ? |
| Configuration | Quelles variables `.env` activent la source ? |
| Appels | Quels endpoints/pages sont utilisés ? |
| Mapping | Quels champs alimentent `RawJob` et `source_data` ? |
| Stratégie filtre | Quels `FilterFacts` sont fiables pour rejeter ou garder ? |
| Stratégie analyse | Qu'est-ce que le LLM reçoit vraiment ? |

Objectif : séparer les données brutes, les faits de filtre et les informations
envoyées au LLM, sans noyer la lecture dans les détails d'implémentation.

Sources documentées :

- [SerpAPI / Google Jobs](serpapi.md)
- [France Travail](francetravail.md)
- [LinkedIn via Apify](linkedin.md)
- [Welcome to the Jungle](welcometothejungle.md)
