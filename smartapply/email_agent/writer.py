"""Legacy LLM writer for a concise motivation letter."""

from __future__ import annotations

from smartapply.llm import EmailDraft, JobAnalysis, LLMProvider, get_llm_provider
from smartapply.llm.prompts import email_writer
from smartapply.profile import Profile


class EmailWriter:
    def __init__(self, profile: Profile, llm: LLMProvider | None = None):
        self.profile = profile
        self.llm = llm or get_llm_provider()

    def write(
        self,
        *,
        analysis: JobAnalysis,
        job_title: str,
        job_company: str,
        language: str = "fr",
        job_id: int | None = None,
    ) -> EmailDraft:
        prompt = email_writer.build_user_prompt(
            profile=self.profile,
            analysis=analysis,
            job_title=job_title,
            job_company=job_company,
            language=language,
        )
        return self.llm.complete_json(
            system=email_writer.SYSTEM,
            user=prompt,
            schema=EmailDraft,
            model=self.llm.cheap_model,
            temperature=0.5,
            purpose="email_writer",
            job_id=job_id,
        )
