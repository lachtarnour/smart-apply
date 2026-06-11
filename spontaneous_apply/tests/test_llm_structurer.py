from __future__ import annotations

from spontaneous_apply.src.llm_structurer import parse_structured_profile


def test_parse_structured_profile_validates_json() -> None:
    profile = parse_structured_profile(
        """
        {
          "company_name": "Sonio",
          "sector": "MedTech / HealthTech",
          "sub_sector": "IA clinique",
          "short_description": "Sonio développe une solution d'IA clinique.",
          "detailed_description": null,
          "products_or_services": ["solution d'IA clinique"],
          "target_users": ["professionnels de santé"],
          "business_model": "SaaS B2B médical",
          "ai_data_relevance": ["IA médicale"],
          "tech_keywords": ["machine learning"],
          "health_keywords": ["diagnostic prénatal"],
          "what_they_look_for": null,
          "good_to_know": null,
          "candidate_fit_score": 9,
          "candidate_fit_reason": "Très bon alignement avec l'IA appliquée à la santé.",
          "personalization_anchor": "votre travail autour de l'IA clinique",
          "email_angle": "Mettre en avant l'expérience en données cliniques.",
          "confidence": "high",
          "risk_notes": null
        }
        """
    )

    assert profile.company_name == "Sonio"
    assert profile.candidate_fit_score == 9

