"""HTML templates and PDF rendering for application documents.

The generated CV follows the architecture of the reference PDF:
header, italic summary, contact line, blue section labels with black rules,
two-column experience/education rows, then compact skills/projects/languages.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
import re

from jinja2 import Environment, FileSystemLoader, select_autoescape

from smartapply.cv.links import render_bullet_html
from smartapply.llm import AdaptedCV, EmailDraft
from smartapply.profile import Profile


TEMPLATES_DIR = Path(__file__).with_name("templates")
MIN_PROJECTS = 3

_PDF_COUNT_RE = re.compile(rb"/Count\s+(\d+)")


def _chrome_executable() -> str | None:
    candidates = [
        shutil.which("google-chrome"),
        shutil.which("google-chrome-stable"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    return None


def html_to_pdf(html: str, pdf_path: str | Path, *, base_dir: str | Path | None = None) -> Path:
    """Render HTML to PDF with WeasyPrint when installed, otherwise Chrome.

    Chrome is intentionally supported because it is commonly available on the
    user's Mac and avoids forcing heavy system dependencies for a first V1.
    """
    pdf_path = Path(pdf_path).resolve()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        from weasyprint import HTML  # type: ignore

        HTML(string=html, base_url=str(base_dir or TEMPLATES_DIR)).write_pdf(str(pdf_path))
        return pdf_path
    except ImportError:
        pass

    chrome = _chrome_executable()
    if not chrome:
        raise RuntimeError(
            "PDF rendering requires WeasyPrint or Chrome/Chromium. "
            "Install one of them, then rerun the command."
        )

    with tempfile.NamedTemporaryFile(
        "w",
        suffix=".html",
        encoding="utf-8",
        delete=False,
        dir=str(pdf_path.parent),
    ) as tmp:
        tmp.write(html)
        tmp_html = Path(tmp.name)

    try:
        subprocess.run(
            [
                chrome,
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--no-pdf-header-footer",
                f"--print-to-pdf={pdf_path}",
                tmp_html.resolve().as_uri(),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    finally:
        tmp_html.unlink(missing_ok=True)

    return pdf_path


def pdf_page_count(pdf_path: str | Path) -> int:
    """Best-effort page count without adding a heavy PDF dependency."""
    data = Path(pdf_path).read_bytes()
    counts = [int(match.group(1)) for match in _PDF_COUNT_RE.finditer(data)]
    if counts:
        return max(counts)
    return max(1, len(re.findall(rb"/Type\s*/Page\b", data)))


@dataclass(frozen=True)
class RenderedApplicationDocuments:
    cv_html_path: Path
    cv_pdf_path: Path
    letter_html_path: Path
    letter_pdf_path: Path


class HtmlApplicationRenderer:
    """Render CV and motivation letter HTML/PDF documents."""

    def __init__(self, profile: Profile):
        self.profile = profile
        self.env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=select_autoescape(("html", "xml", "j2")),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    @property
    def pdf_available(self) -> bool:
        try:
            import weasyprint  # noqa: F401

            return True
        except ImportError:
            return _chrome_executable() is not None

    def render_cv_html(self, adapted: AdaptedCV, *, force_one_page: bool = False) -> str:
        template = self.env.get_template("cv.html.j2")
        exp_by_id = {exp.id: exp for exp in self.profile.experiences}
        project_by_id = {project.id: project for project in self.profile.projects}

        experiences = []
        total_bullets = 0
        for adapted_exp in adapted.selected_experiences:
            source = exp_by_id.get(adapted_exp.source_id)
            if source:
                max_bullets = self._max_bullets_for_experience(
                    index=len(experiences),
                    selected_project_count=len(adapted.selected_project_ids),
                    force_one_page=force_one_page,
                )
                remaining = self._max_total_bullets(
                    selected_project_count=len(adapted.selected_project_ids),
                    force_one_page=force_one_page,
                ) - total_bullets
                if remaining <= 0:
                    break
                bullets = adapted_exp.bullets[: min(max_bullets, remaining)]
                if bullets:
                    total_bullets += len(bullets)
                    source_links_by_id = {b.id: b.links for b in source.bullets}
                    bullets_view = [
                        {
                            "text": b.text,
                            "html": render_bullet_html(
                                b.text,
                                source_links_by_id.get(b.source_id, []),
                            ),
                        }
                        for b in bullets
                    ]
                    experiences.append(
                        {
                            "source": source,
                            "bullets": bullets_view,
                        }
                    )
            if len(experiences) >= 3:
                break

        selected_projects = self._select_projects(
            adapted=adapted,
            project_by_id=project_by_id,
            force_one_page=force_one_page,
        )
        skill_categories = self._skill_categories_for(adapted)
        layout_class = self._layout_class(
            experiences=experiences,
            projects=selected_projects,
            skill_categories=skill_categories,
            force_one_page=force_one_page,
        )

        return template.render(
            profile=self.profile,
            adapted=adapted,
            experiences=experiences,
            education=list(self.profile.education),
            skill_categories=skill_categories,
            projects=selected_projects,
            languages=list(self.profile.languages),
            certificates=list(self.profile.certificates),
            contact_line=self._contact_line(),
            contact_items=self._contact_items(),
            layout_class=layout_class,
        )

    def render_letter_html(
        self,
        *,
        email_draft: EmailDraft,
        job_title: str,
        job_company: str,
        contact_email: str | None = None,
        language: str = "fr",
    ) -> str:
        template = self.env.get_template("motivation_letter.html.j2")
        labels = self._letter_labels(language)
        paragraphs = [
            paragraph.strip()
            for paragraph in email_draft.body.replace("\r\n", "\n").split("\n\n")
            if paragraph.strip()
        ]
        return template.render(
            profile=self.profile,
            subject=email_draft.subject,
            paragraphs=paragraphs,
            job_title=job_title,
            job_company=job_company,
            contact_email=contact_email,
            contact_line=self._contact_line(),
            contact_items=self._contact_items(),
            labels=labels,
        )

    def save_cv_html(self, adapted: AdaptedCV, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.render_cv_html(adapted), encoding="utf-8")
        return path

    def save_letter_html(
        self,
        *,
        email_draft: EmailDraft,
        job_title: str,
        job_company: str,
        path: str | Path,
        contact_email: str | None = None,
        language: str = "fr",
    ) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        html = self.render_letter_html(
            email_draft=email_draft,
            job_title=job_title,
            job_company=job_company,
            contact_email=contact_email,
            language=language,
        )
        path.write_text(html, encoding="utf-8")
        return path

    def save_cv_pdf(self, adapted: AdaptedCV, path: str | Path) -> Path:
        path = html_to_pdf(self.render_cv_html(adapted), path, base_dir=TEMPLATES_DIR)
        if pdf_page_count(path) > 1:
            path = html_to_pdf(
                self.render_cv_html(adapted, force_one_page=True),
                path,
                base_dir=TEMPLATES_DIR,
            )
        return path

    def save_letter_pdf(
        self,
        *,
        email_draft: EmailDraft,
        job_title: str,
        job_company: str,
        path: str | Path,
        contact_email: str | None = None,
        language: str = "fr",
    ) -> Path:
        html = self.render_letter_html(
            email_draft=email_draft,
            job_title=job_title,
            job_company=job_company,
            contact_email=contact_email,
            language=language,
        )
        return html_to_pdf(html, path, base_dir=TEMPLATES_DIR)

    def _contact_line(self) -> str:
        return "  |  ".join(item["label"] for item in self._contact_items())

    def _contact_items(self) -> list[dict[str, str | None]]:
        identity = self.profile.identity
        bits = [
            {"label": identity.location, "href": None},
            {"label": identity.phone, "href": None} if identity.phone else None,
            {"label": str(identity.email), "href": f"mailto:{identity.email}"},
            {"label": "GitHub", "href": str(identity.github)} if identity.github else None,
            {"label": "LinkedIn", "href": str(identity.linkedin)} if identity.linkedin else None,
            (
                {"label": self._display_url(str(identity.website)), "href": str(identity.website)}
                if identity.website
                else None
            ),
        ]
        return [bit for bit in bits if bit and bit["label"]]

    def _skill_categories_for(self, adapted: AdaptedCV) -> list[dict[str, list[str] | str]]:
        selected_rows = self._selected_skill_rows(adapted)
        if selected_rows:
            return selected_rows

        profile_id = (
            adapted.skills_profile_id
            if self.profile.skills.profile_by_id(adapted.skills_profile_id) is not None
            else self._infer_skill_profile_id(adapted)
        )

        by_id = {category.id: category for category in self.profile.skills.categories}
        merged = self.profile.skills.effective_category_skills(profile_id)
        rows = []
        for category_id, skills in merged.items():
            category = by_id.get(category_id)
            if category and skills:
                rows.append({"name": category.name, "skills": skills})
        if rows:
            return rows

        ordered_ids = [cid for cid in adapted.skills_order if cid in by_id] + [
            cid for cid in by_id if cid not in adapted.skills_order
        ]
        return [
            {
                "name": by_id[cid].name,
                "skills": self._select_display_skills(by_id[cid], adapted),
            }
            for cid in ordered_ids
        ]

    def _select_projects(
        self,
        *,
        adapted: AdaptedCV,
        project_by_id: dict[str, object],
        force_one_page: bool,
    ) -> list[object]:
        """Always render a useful project section, with at least 3 real projects.

        The LLM still controls priority through ``selected_project_ids``. When it
        gives too few projects, we fill from the source profile using keyword
        overlap with the adapted CV, then the original profile order.
        """
        max_projects = self._max_projects(force_one_page=force_one_page)
        selected: list[object] = []
        seen: set[str] = set()
        for project_id in adapted.selected_project_ids:
            project = project_by_id.get(project_id)
            if project is not None and project_id not in seen:
                selected.append(project)
                seen.add(project_id)
            if len(selected) >= max_projects:
                return selected

        min_projects = min(MIN_PROJECTS, max_projects, len(project_by_id))
        if len(selected) >= min_projects:
            return selected[:max_projects]

        context = self._adapted_context(adapted)
        remaining = [
            project
            for project_id, project in project_by_id.items()
            if project_id not in seen
        ]
        remaining.sort(
            key=lambda project: self._project_relevance(project, context),
            reverse=True,
        )
        for project in remaining:
            selected.append(project)
            if len(selected) >= min_projects:
                break
        return selected[:max_projects]

    @staticmethod
    def _project_relevance(project, context: str) -> tuple[int, int]:
        keywords = [kw.lower() for kw in getattr(project, "keywords", [])]
        name_tokens = re.findall(r"[a-z0-9]+", getattr(project, "name", "").lower())
        description_tokens = re.findall(r"[a-z0-9]+", getattr(project, "description", "").lower())
        score = sum(1 for keyword in keywords if keyword and keyword in context)
        score += sum(1 for token in name_tokens if len(token) > 2 and token in context)
        score += sum(1 for token in description_tokens if len(token) > 4 and token in context)
        # Stable tie-breaker that keeps source-profile order via Python's stable sort.
        return (score, len(keywords))

    def _infer_skill_profile_id(self, adapted: AdaptedCV) -> str:
        context = self._adapted_context(adapted)
        for profile_id in (
            "medical_ai",
            "reinforcement_learning",
            "computer_vision",
            "speech_audio",
            "llm",
            "time_series",
            "data_analyst",
            "machine_learning",
        ):
            if profile_id in self.profile.skills.profile_ids and any(
                keyword.lower() in context
                for keyword in self.profile.skills.matching_keywords.get(profile_id, [])
            ):
                return profile_id
        # Order from most specific to most general. Niche signals dominate.
        if any(token in context for token in ("reinforcement", "openai gym", "agent training", "control task")):
            return "reinforcement_learning"
        if any(token in context for token in ("clinical", "medical", "digital health", "biomarker", "healthtech", "medtech")):
            return "medical_ai"
        if any(token in context for token in ("computer vision", "image classification", "object detection", "segmentation", "face recognition")):
            return "computer_vision"
        if any(token in context for token in ("llm", "rag", "nlp", "language model", "transformer", "embedding model", "retrieval")):
            return "llm"
        if any(token in context for token in ("forecasting", "time series", "time-series", "anomaly detection", "arima", "kalman")):
            return "time_series"
        if any(token in context for token in ("data analyst", "analytics", "dashboard", "kpi", "reporting", "product analyst")):
            return "data_analyst"
        if any(token in context for token in ("ml engineer", "deployment", "production", "mlops", "model serving", "data pipeline")):
            return "machine_learning"
        return "mixed"

    def _select_display_skills(self, category, adapted: AdaptedCV) -> list[str]:
        """Surface CV-relevant skills first without applying an arbitrary cap."""
        context = self._adapted_context(adapted)
        matched = [skill for skill in category.skills if skill.lower() in context]
        rest = [skill for skill in category.skills if skill not in matched]
        return matched + rest

    def _selected_skill_rows(self, adapted: AdaptedCV) -> list[dict[str, list[str] | str]]:
        if not adapted.selected_skills:
            return []
        by_id = {category.id: category for category in self.profile.skills.categories}
        canonical = {skill.lower(): skill for skill in self.profile.skills.allowed_skills}
        ordered_ids = [cid for cid in adapted.skills_order if cid in by_id] + [
            block.category_id
            for block in adapted.selected_skills
            if block.category_id in by_id and block.category_id not in adapted.skills_order
        ]
        selected_by_category = {
            block.category_id: block.skills for block in adapted.selected_skills
        }
        rows: list[dict[str, list[str] | str]] = []
        for cid in ordered_ids:
            category = by_id[cid]
            skills: list[str] = []
            seen: set[str] = set()
            for skill in selected_by_category.get(cid, []):
                canonical_skill = canonical.get(skill.lower())
                if canonical_skill and canonical_skill not in seen:
                    skills.append(canonical_skill)
                    seen.add(canonical_skill)
            if skills:
                rows.append({"name": category.name, "skills": skills})
        return rows

    @staticmethod
    def _adapted_context(adapted: AdaptedCV) -> str:
        context_bits = [
            adapted.cv_title,
            adapted.professional_summary,
            " ".join(adapted.selected_project_ids),
            " ".join(
                bullet.text
                for exp in adapted.selected_experiences
                for bullet in exp.bullets
            ),
        ]
        return " ".join(context_bits).lower()

    @staticmethod
    def _max_bullets_for_experience(
        *,
        index: int,
        selected_project_count: int,
        force_one_page: bool,
    ) -> int:
        if force_one_page:
            return 3 if index == 0 else 1
        if selected_project_count >= 4:
            return 4 if index == 0 else 1
        return 4 if index == 0 else 2

    @staticmethod
    def _max_total_bullets(*, selected_project_count: int, force_one_page: bool) -> int:
        if force_one_page:
            return 5
        if selected_project_count >= 4:
            return 6
        return 7

    @staticmethod
    def _max_projects(*, force_one_page: bool) -> int:
        return 4 if force_one_page else 5

    @staticmethod
    def _layout_class(
        *,
        experiences: list[dict],
        projects: list,
        skill_categories: list[dict[str, list[str] | str]],
        force_one_page: bool,
    ) -> str:
        if force_one_page:
            return "cv-ultra"
        bullet_count = sum(len(item["bullets"]) for item in experiences)
        skill_count = sum(len(row["skills"]) for row in skill_categories)
        density = (
            len(experiences) * 1.4
            + bullet_count * 0.9
            + len(projects) * 0.8
            + skill_count * 0.12
        )
        # Density bands tuned so the page fills naturally — lower density gets
        # bigger line-height + entry-gap + section-gap so the whitespace spreads
        # across the document instead of pooling at the bottom.
        if density <= 9:
            return "cv-very-airy"
        if density <= 13:
            return "cv-airy"
        if density >= 17:
            return "cv-compact"
        return "cv-balanced"

    @staticmethod
    def _display_url(url: str) -> str:
        return url.removeprefix("https://").removeprefix("http://").rstrip("/")

    @staticmethod
    def _letter_labels(language: str) -> dict[str, str]:
        if language == "en":
            return {
                "document_title": "Motivation Letter",
                "role": "Role",
                "contact": "Contact",
                "subject": "Subject",
                "separator": ":",
            }
        return {
            "document_title": "Lettre de motivation",
            "role": "Poste",
            "contact": "Contact",
            "subject": "Objet",
            "separator": " :",
        }
