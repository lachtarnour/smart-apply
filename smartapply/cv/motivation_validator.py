"""Light validation for generated motivation letters."""

from __future__ import annotations

import re

from unidecode import unidecode

from smartapply.cv.constants import NON_DISPLAY_DOMAIN_TERMS
from smartapply.cv.validator import ValidationResult
from smartapply.llm import AdaptedCV, JobAnalysis, MotivationLetter
from smartapply.profile import Profile

_SELF_DEPRECATION_PATTERNS = {
    "although_gap": r"\b(although|even though|while)\b[^.]{0,120}\b(i|my|this profile)\b[^.]{0,120}\b(do not|don't|does not|lack|lacks|limited|still learning|new to)\b",
    "no_experience_en": r"\b(i|my profile)\b[^.]{0,80}\b(do not|don't|have not|haven't|lack|lacks)\b[^.]{0,80}\b(experience|knowledge|expertise)\b",
    "limited_knowledge_en": r"\b(limited knowledge|limited experience|still learning|ready to learn|willing to learn|learning curve)\b",
    "aware_gap_en": r"\b(i am aware|i recognize|i acknowledge|i understand)\b[^.]{0,140}\b(requires?|may require|could require|limited|lack|gap)\b",
    "bien_que_fr": r"\b(bien que|même si)\b[^.]{0,160}\b(je|mon profil|ma connaissance|mon expérience)\b[^.]{0,160}\b(n['’]ai[e]? pas|soit limitée?|reste limitée?|manque|début de carrière|dois apprendre)\b",
    "je_nai_pas_fr": r"\bje n['’]ai[e]? pas\b[^.]{0,120}\b(expérience|connaissance|expertise|encore)\b",
    "limite_fr": r"\b(connaissance limitée|expérience limitée|expérience directe limitée|domaine que je n['’]ai pas encore exploré)\b",
    "aware_gap_fr": r"\b(je suis conscient|je reconnais|je comprends)\b[^.]{0,160}\b(nécessite|requiert|pourrait|peut nécessiter|limitée?|manque|plus approfondie)\b",
    "ready_to_learn_fr": r"\b(prêt(?:e)? à apprendre|disposé(?:e)? à apprendre|m['’]adapter et à apprendre|en train de me former)\b",
}

_UNSUPPORTED_TECH_TERMS = {
    ".net",
    "angular",
    "ansible",
    "asp.net",
    "azure",
    "bigquery",
    "c#",
    "dataiku",
    "dataiku dss",
    "dbt",
    "digdag",
    "digdash",
    "gcp",
    "google cloud",
    "java",
    "kubernetes",
    "microsoft copilot studio",
    "power bi",
    "react",
    "spring",
    "spring boot",
    "tableau",
    "terraform",
    "typescript",
}

_SUPPORTED_TERM_ALIASES = {
    "api rest": ("fastapi", "flask"),
    "deep learning": ("pytorch", "tensorflow", "cnns"),
    "machine learning": ("pytorch", "tensorflow", "scikit-learn"),
    "prevision": ("forecasting",),
    "prévision": ("forecasting",),
    "preparation de donnees": ("pandas", "polars"),
    "préparation de données": ("pandas", "polars"),
    "reporting": ("streamlit",),
    "series temporelles": (
        "time-series",
        "time-series analysis",
        "time-series modeling",
        "arima/sarima",
    ),
    "séries temporelles": (
        "time-series",
        "time-series analysis",
        "time-series modeling",
        "arima/sarima",
    ),
    "statistiques": ("statistical modeling", "statistical analysis"),
    "traitement statistique de donnees": ("statistical analysis", "statistical modeling"),
    "traitement statistique de données": ("statistical analysis", "statistical modeling"),
    "data engineering": ("spark",),
    "data engineer": ("spark",),
    "etl/elt": ("spark",),
}

_PROJECT_ALIASES = {
    "proj_svc": (
        "singing voice conversion",
        "svc",
        "conversion de voix chantée",
        "conversion de voix chantee",
        "modélisation acoustique",
        "modelisation acoustique",
    ),
    "proj_scifact_rag": ("scifact", "scifact rag verifier"),
    "proj_smartapply": ("smartapply", "smart apply"),
    "proj_bot_traffic_anomaly": ("bot traffic anomaly detection",),
    "proj_aal_stock_forecasting": ("aal stock forecasting", "american airlines group"),
    "proj_gpt2": ("gpt-2-style language model", "gpt-2"),
    "proj_ner_camembert": ("ner with bert", "bert base cased", "conll-2003"),
    "proj_rl_gym": ("reinforcement learning algorithm", "openai gym"),
}

_FOREIGN_SCRIPT_RANGES = {
    "arabic": r"\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF",
    "armenian": r"\u0530-\u058F",
    "cyrillic": r"\u0400-\u04FF",
    "hebrew": r"\u0590-\u05FF",
    "cjk": r"\u3040-\u30FF\u3400-\u4DBF\u4E00-\u9FFF\uAC00-\uD7AF",
}


def _normalize(text: str) -> str:
    return " ".join((text or "").lower().split())


def _alias_keys(term: str) -> set[str]:
    normalized = _normalize(term)
    return {normalized, unidecode(normalized)}


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text or ""))


def _paragraph_count(text: str) -> int:
    paragraphs = re.split(r"\n\s*\n+", (text or "").strip())
    return len([paragraph for paragraph in paragraphs if paragraph.strip()])


def normalize_french_elisions(text: str, *, language: str = "fr") -> str:
    """Repair common missing French apostrophes without ASCII-folding text."""
    if language != "fr" or not text:
        return text

    def one_letter(match: re.Match[str]) -> str:
        prefix = match.group(1)
        word = match.group(2)
        return f"{prefix}'{word}"

    fixed = text
    # j ai -> j'ai, d AI -> d'AI, l IA -> l'IA, m ont -> m'ont, ...
    fixed = re.sub(
        r"(?<![A-Za-zÀ-ÖØ-öø-ÿ&-])\b([cdjlmnstCDJLMNST])\s+([A-Za-zÀ-ÖØ-öø-ÿ][\wÀ-ÖØ-öø-ÿ-]*)",
        one_letter,
        fixed,
    )

    phrase_replacements = (
        (r"\b[qQ]u\s+([A-Za-zÀ-ÖØ-öø-ÿ][\wÀ-ÖØ-öø-ÿ-]*)", "qu'{}"),
        (r"\b[jJ]usqu\s+([A-Za-zÀ-ÖØ-öø-ÿ][\wÀ-ÖØ-öø-ÿ-]*)", "jusqu'{}"),
        (r"\b[lL]orsqu\s+([A-Za-zÀ-ÖØ-öø-ÿ][\wÀ-ÖØ-öø-ÿ-]*)", "lorsqu'{}"),
        (r"\b[pP]uisqu\s+([A-Za-zÀ-ÖØ-öø-ÿ][\wÀ-ÖØ-öø-ÿ-]*)", "puisqu'{}"),
    )
    for pattern, replacement in phrase_replacements:
        fixed = re.sub(
            pattern,
            lambda m, repl=replacement: repl.format(m.group(1)),
            fixed,
        )
    fixed = re.sub(r"\b[Aa]ujourd\s+hui\b", "aujourd'hui", fixed)
    return fixed


_MISSING_APOSTROPHE_PATTERNS = (
    r"(?<![A-Za-zÀ-ÖØ-öø-ÿ&-])\b[cdjlmnstCDJLMNST]\s+[A-Za-zÀ-ÖØ-öø-ÿ]",
    r"\b[qQ]u\s+[A-Za-zÀ-ÖØ-öø-ÿ]",
    r"\b[jJ]usqu\s+[A-Za-zÀ-ÖØ-öø-ÿ]",
    r"\b[lL]orsqu\s+[A-Za-zÀ-ÖØ-öø-ÿ]",
    r"\b[pP]uisqu\s+[A-Za-zÀ-ÖØ-öø-ÿ]",
    r"\b[Aa]ujourd\s+hui\b",
)

_CANDIDATE_CLAIM_PATTERNS = (
    r"\bmy\s+(?:background|experience|expertise|skills?|work|projects?|profile)\b",
    r"\bmon\s+(?:parcours|profil|travail|projet|expérience|experience)\b",
    r"\bma\s+(?:pratique|contribution|maitrise|maîtrise|connaissance|compétence|competence)\b",
    r"\bmes\s+(?:compétences|competences|projets|travaux|expériences|experiences)\b",
    r"\b(?:i|we)\s+(?:built|build|developed|develop|designed|design|trained|train|implemented|implement|used|use|worked|work|created|create|contributed|contribute)\b",
    r"\bj['’]ai\s+(?:conçu|concu|développé|developpe|utilisé|utilise|construit|bâti|bati|entraîné|entraine|implémenté|implemente|travaillé|travaille|contribué|contribue)\b",
    r"\bchez\s+emobot\b",
)


def mentioned_project_ids(text: str, profile: Profile) -> list[str]:
    """Return profile project ids explicitly named or aliased in text."""
    body_lower = _normalize(text)
    mentioned: list[str] = []
    for project in profile.projects:
        aliases = set(_PROJECT_ALIASES.get(project.id, ()))
        aliases.add(project.name)
        normalized_aliases = [
            _normalize(alias)
            for alias in aliases
            if len(_normalize(alias)) >= 4
        ]
        if any(alias in body_lower for alias in normalized_aliases):
            mentioned.append(project.id)
    return mentioned


class MotivationLetterValidator:
    """Check that the letter stays tied to selected profile evidence."""

    def __init__(self, profile: Profile, min_words: int = 220, max_words: int = 300):
        self.profile = profile
        self.min_words = min_words
        self.max_words = max_words
        self.allowed_skills = profile.skills.allowed_skills
        self.projects_by_id = {p.id: p for p in profile.projects}
        self.experiences_by_id = {e.id: e for e in profile.experiences}
        self.allowed_terms = self._profile_allowed_terms()

    def validate(
        self,
        letter: MotivationLetter,
        *,
        cv: AdaptedCV,
        analysis: JobAnalysis,
    ) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        body_lower = _normalize(letter.body)

        for label in self._foreign_scripts(letter.body):
            errors.append(f"foreign_script_in_letter:{label}")

        paragraph_count = _paragraph_count(letter.body)
        if paragraph_count != 3:
            warnings.append(f"letter_not_3_paragraphs:{paragraph_count}")

        count = _word_count(letter.body)
        min_words = self.min_words
        max_words = self.max_words
        if count < min_words:
            warnings.append(f"letter_too_short:{count}")
        if count > max_words:
            warnings.append(f"letter_too_long:{count}")

        for term in self._unsupported_offer_terms(analysis):
            if self._term_used_as_candidate_claim(letter.body, term):
                warnings.append(f"unsupported_term_in_letter:{term}")

        for label, pattern in _SELF_DEPRECATION_PATTERNS.items():
            if re.search(pattern, body_lower, flags=re.IGNORECASE):
                warnings.append(f"letter_self_deprecation:{label}")

        if (analysis.offer_language or "fr").lower().startswith("fr"):
            for pattern in _MISSING_APOSTROPHE_PATTERNS:
                if re.search(pattern, letter.body):
                    warnings.append("french_elision_missing_apostrophe")
                    break

        for term in self._unsupported_tech_terms(letter.body):
            warnings.append(f"unsupported_tech_in_letter:{term}")

        for project_id in self._unselected_projects_mentioned(body_lower, cv):
            warnings.append(f"unselected_project_in_letter:{project_id}")

        if not self._references_selected_evidence(body_lower, cv):
            warnings.append("letter_may_not_reference_selected_evidence")

        return ValidationResult(ok=not errors, errors=errors, warnings=warnings)

    def _foreign_scripts(self, text: str) -> list[str]:
        found: list[str] = []
        for label, char_range in _FOREIGN_SCRIPT_RANGES.items():
            if re.search(f"[{char_range}]", text or ""):
                found.append(label)
        return found

    def _unsupported_offer_terms(self, analysis: JobAnalysis) -> list[str]:
        terms: list[str] = []
        seen: set[str] = set()
        for raw in list(analysis.required_skills) + list(analysis.cv_keywords_to_include):
            term = " ".join((raw or "").split())
            key = term.lower()
            if not term or key in seen or key in NON_DISPLAY_DOMAIN_TERMS:
                continue
            seen.add(key)
            if self._term_supported_by_allowed_skill(term):
                continue
            if self._term_supported_by_profile_evidence(term):
                continue
            terms.append(term)
        return terms

    def _term_supported_by_allowed_skill(self, term: str) -> bool:
        normalized = _normalize(term)
        alias_terms = {
            alias
            for key in _alias_keys(term)
            for alias in _SUPPORTED_TERM_ALIASES.get(key, ())
        }
        for skill in self.allowed_skills:
            skill_norm = _normalize(skill)
            if not skill_norm:
                continue
            if normalized == skill_norm or skill_norm in alias_terms:
                return True
            if len(skill_norm) > 2 and (skill_norm in normalized or normalized in skill_norm):
                return True
        return False

    def _term_supported_by_profile_evidence(self, term: str) -> bool:
        normalized = _normalize(term)
        if not normalized:
            return False
        alias_terms = {
            alias
            for key in _alias_keys(term)
            for alias in _SUPPORTED_TERM_ALIASES.get(key, ())
        }
        if any(alias in self.allowed_terms for alias in alias_terms):
            return True
        for allowed in self.allowed_terms:
            if len(allowed) <= 2:
                continue
            if normalized == allowed or allowed in normalized or normalized in allowed:
                return True
        return False

    def _profile_allowed_terms(self) -> set[str]:
        terms = {_normalize(skill) for skill in self.allowed_skills}
        for project in self.profile.projects:
            terms.add(_normalize(project.name))
            terms.update(_normalize(keyword) for keyword in project.keywords)
        for exp in self.profile.experiences:
            terms.add(_normalize(exp.company))
            terms.add(_normalize(exp.title))
            terms.update(_normalize(keyword) for keyword in exp.keywords)
            for bullet in exp.bullets:
                terms.update(_normalize(keyword) for keyword in bullet.keywords)
                terms.update(_normalize(claim) for claim in bullet.effective_allowed_claims)
        return {term for term in terms if term}

    def _unsupported_tech_terms(self, body_lower: str) -> list[str]:
        found: list[str] = []
        for term in sorted(_UNSUPPORTED_TECH_TERMS):
            term_norm = _normalize(term)
            if term_norm in self.allowed_terms:
                continue
            if self._term_used_as_candidate_claim(body_lower, term):
                found.append(term)
        return found

    def _term_used_as_candidate_claim(self, text: str, term: str) -> bool:
        term_norm = _normalize(term)
        if not term_norm:
            return False

        for sentence in re.split(r"(?<=[.!?])\s+|\n+", text or ""):
            sentence_norm = _normalize(sentence)
            if not re.search(
                rf"(?<![a-z0-9+#]){re.escape(term_norm)}(?![a-z0-9+#])",
                sentence_norm,
            ):
                continue
            if any(
                re.search(pattern, sentence_norm, flags=re.IGNORECASE)
                for pattern in _CANDIDATE_CLAIM_PATTERNS
            ):
                return True
        return False

    def _unselected_projects_mentioned(self, body_lower: str, cv: AdaptedCV) -> list[str]:
        selected = set(cv.selected_project_ids)
        return [
            project_id
            for project_id in mentioned_project_ids(body_lower, self.profile)
            if project_id not in selected
        ]

    def _references_selected_evidence(self, body_lower: str, cv: AdaptedCV) -> bool:
        evidence_terms: set[str] = set()
        for project_id in cv.selected_project_ids:
            project = self.projects_by_id.get(project_id)
            if project:
                evidence_terms.add(project.name)
                evidence_terms.update(project.keywords[:4])
            evidence_terms.add(project_id)

        for exp in cv.selected_experiences:
            source = self.experiences_by_id.get(exp.source_id)
            if source:
                evidence_terms.add(source.company)
                evidence_terms.add(source.title)
                evidence_terms.update(source.keywords[:4])
            evidence_terms.add(exp.source_id)
            for bullet in exp.bullets:
                evidence_terms.add(bullet.source_id)

        normalized_terms = [
            _normalize(term)
            for term in evidence_terms
            if len(_normalize(term)) >= 4
        ]
        return any(term in body_lower for term in normalized_terms)
