"""Generate CV PDFs for 20 real offers using the V1.2 contract + new spacing.

Pulls the analyses from the prod DB (cached), runs CvAdapter.adapt with LLM,
applies the role-family contract, validates, renders HTML + PDF.

Output: /tmp/test_20_offers/<job_id>/{CV.pdf, CV.html, summary.json}
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from smartapply.cv import CvAdapter, CvValidator, HtmlApplicationRenderer  # noqa: E402
from smartapply.cv.html_renderer import pdf_page_count  # noqa: E402
from smartapply.cv.role_family import classify  # noqa: E402
from smartapply.llm import JobAnalysis  # noqa: E402
from smartapply.profile import get_profile  # noqa: E402


JOB_IDS: list[int] = [
    126,  # Product Data Analyst — data_analyst
    359,  # ML Engineer Speech Processing — speech_audio
    400,  # ML Engineer / MLOps — mlops
    464,  # Pathway End-to-End ML — ml_engineer
    465,  # Smart Traffik Backend — software_engineer
    473,  # ELA Technology Data Scientist — data_scientist (LLM?)
    481,  # Boulanger Data Scientist — data_scientist
    487,  # CLS Data Scientist altimétrie — data_scientist
    489,  # SILKHOM DS-IA automobile — data_scientist
    491,  # Wavestone Data Scientist — data_scientist
    492,  # Banque de France DS sondages — data_scientist
    500,  # Orange Wholesale Cloud Data Engineer — ml_engineer?
    507,  # STORYZY Full Stack AI SWE — software_engineer
    515,  # Wavestone AI Engineer — llm_engineer
    525,  # BASSETTI AI Eng / Test — llm_engineer/ml_engineer
    534,  # SAS NG DevOps — other/mlops
    537,  # Sopra Steria Java Manager — software_engineer
    539,  # KLANIK Generative AI — llm_engineer
    546,  # LEA Computer Vision — computer_vision
    555,  # IAM Engineer — software_engineer/other
]

OUTPUT_DIR = Path("/tmp/test_20_offers")
DB_PATH = REPO_ROOT / "data" / "smartapply.db"


def _json_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        v = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return v if isinstance(v, list) else []


def _load_jobs() -> list[dict]:
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    qs = ",".join("?" * len(JOB_IDS))
    cur.execute(
        f"""
        SELECT j.id, j.title, j.company, j.location,
            ja.role_type, ja.seniority, ja.domain, ja.main_tasks,
            ja.required_skills, ja.nice_to_have, ja.match_reasons,
            ja.risks, ja.cv_keywords_to_include
        FROM jobs j JOIN job_analyses ja ON ja.job_id=j.id
        WHERE j.id IN ({qs})
        ORDER BY j.id
        """,
        JOB_IDS,
    )
    out = []
    for r in cur.fetchall():
        out.append(
            {
                "id": r["id"],
                "title": r["title"] or "",
                "company": r["company"] or "",
                "analysis": JobAnalysis(
                    role_type=r["role_type"] or "",
                    seniority=r["seniority"] or "mid",
                    domain=r["domain"] or "",
                    main_tasks=_json_list(r["main_tasks"]),
                    required_skills=_json_list(r["required_skills"]),
                    nice_to_have=_json_list(r["nice_to_have"]),
                    match_reasons=_json_list(r["match_reasons"]),
                    risks=_json_list(r["risks"]),
                    cv_keywords_to_include=_json_list(r["cv_keywords_to_include"]),
                ),
            }
        )
    return out


def main() -> None:
    profile = get_profile()
    adapter = CvAdapter(profile)
    validator = CvValidator(profile)
    renderer = HtmlApplicationRenderer(profile)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    jobs = _load_jobs()
    print(f"Generating {len(jobs)} CVs into {OUTPUT_DIR}")
    print()

    summary: list[dict] = []
    started = time.time()
    for idx, job in enumerate(jobs, 1):
        job_id = job["id"]
        family = classify(job["analysis"], title=job["title"])
        t0 = time.time()
        try:
            adapted, _selection = adapter.adapt(
                job["analysis"],
                job_title=job["title"],
                job_company=job["company"],
                job_id=job_id,
            )
            cleaned, removed = validator.auto_fix(adapted)
            adapted = cleaned

            job_dir = OUTPUT_DIR / f"job-{job_id}"
            job_dir.mkdir(parents=True, exist_ok=True)
            html_path = job_dir / "CV.html"
            pdf_path = job_dir / "CV.pdf"
            renderer.save_cv_html(adapted, html_path)
            renderer.save_cv_pdf(adapted, pdf_path)
            pages = pdf_page_count(pdf_path)

            selected_skills = [
                {"category_id": b.category_id, "skills": list(b.skills)}
                for b in adapted.selected_skills
            ]
            record = {
                "id": job_id,
                "title": job["title"],
                "company": job["company"],
                "family": family,
                "pages": pages,
                "selected_skills": selected_skills,
                "removed_by_autofix": removed,
                "duration_s": round(time.time() - t0, 1),
            }
            summary.append(record)
            (job_dir / "summary.json").write_text(
                json.dumps(record, indent=2, ensure_ascii=False)
            )

            skills_inline = " | ".join(
                f"{b['category_id']}=[{', '.join(b['skills'])}]"
                for b in selected_skills
            )
            print(
                f"{idx:2d}/{len(jobs)}  job={job_id:3d}  pages={pages}  family={family:18s}"
                f"  {job['title'][:55]}"
            )
            print(f"        skills: {skills_inline}")
        except Exception as exc:  # noqa: BLE001
            print(f"{idx:2d}/{len(jobs)}  job={job_id:3d}  ERROR: {exc}")
            summary.append({"id": job_id, "error": str(exc)})

    elapsed = time.time() - started
    (OUTPUT_DIR / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False)
    )
    print()
    print(f"Done in {elapsed:.1f}s. Summary at {OUTPUT_DIR / 'summary.json'}")


if __name__ == "__main__":
    main()
