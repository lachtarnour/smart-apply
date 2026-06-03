"""Render a sample CV from the eval database to /tmp for visual review."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from smartapply.cv.html_renderer import HtmlApplicationRenderer  # noqa: E402
from smartapply.llm import (  # noqa: E402
    AdaptedBullet,
    AdaptedCV,
    AdaptedExperience,
    SkillSelectionBlock,
)
from smartapply.profile import get_profile  # noqa: E402


DB_PATH = REPO_ROOT / "data" / "skill_eval_30_20260603_161804.db"
OUTPUT_DIR = Path("/tmp/cv_previews")


def _rebuild_cv(cv_json: dict) -> AdaptedCV:
    return AdaptedCV(
        cv_title=cv_json.get("cv_title", ""),
        professional_summary=cv_json.get("professional_summary", ""),
        selected_experiences=[
            AdaptedExperience(
                source_id=exp["source_id"],
                bullets=[
                    AdaptedBullet(source_id=b["source_id"], text=b["text"])
                    for b in exp.get("bullets", [])
                ],
            )
            for exp in cv_json.get("selected_experiences", [])
        ],
        selected_project_ids=cv_json.get("selected_project_ids", []),
        skills_profile_id=cv_json.get("skills_profile_id", ""),
        selected_skills=[
            SkillSelectionBlock(
                category_id=block["category_id"],
                skills=list(block.get("skills", [])),
            )
            for block in cv_json.get("selected_skills", [])
        ],
        skills_order=cv_json.get("skills_order", []),
        warnings=cv_json.get("warnings", []),
    )


def main(job_ids: list[int]) -> None:
    profile = get_profile()
    renderer = HtmlApplicationRenderer(profile)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    for job_id in job_ids:
        cur = con.execute(
            "SELECT j.title, j.company, a.cv_json FROM applications a JOIN jobs j ON a.job_id=j.id WHERE a.job_id=?",
            (job_id,),
        )
        row = cur.fetchone()
        if not row:
            print(f"job={job_id}: not found")
            continue
        cv = _rebuild_cv(json.loads(row["cv_json"]))
        html_path = OUTPUT_DIR / f"cv_job{job_id}.html"
        pdf_path = OUTPUT_DIR / f"cv_job{job_id}.pdf"
        renderer.save_cv_html(cv, html_path)
        renderer.save_cv_pdf(cv, pdf_path)
        print(f"job={job_id} title={row['title'][:50]!r}")
        print(f"  html={html_path}")
        print(f"  pdf={pdf_path}")


if __name__ == "__main__":
    ids = [int(a) for a in sys.argv[1:]] or [4, 25, 57, 72]
    main(ids)
