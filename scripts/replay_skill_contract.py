"""Offline replay of the role-family contract on the 30-jobs benchmark.

We rebuild each AdaptedCV from the LLM output stored in the eval database,
then apply the new contract filter (no LLM call). The script prints a
before/after table so we can see which skills get added or stripped.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from smartapply.cv.role_contracts import apply_contract  # noqa: E402
from smartapply.cv.role_family import classify  # noqa: E402
from smartapply.llm import (  # noqa: E402
    AdaptedCV,
    AdaptedExperience,
    AdaptedBullet,
    JobAnalysis,
    SkillSelectionBlock,
)
from smartapply.profile import get_profile  # noqa: E402


DB_PATH = REPO_ROOT / "data" / "skill_eval_30_20260603_161804.db"


def _json_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


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


def _rebuild_analysis(row: sqlite3.Row) -> JobAnalysis:
    return JobAnalysis(
        role_type=row["role_type"] or "",
        seniority=row["seniority"] or "mid",
        domain=row["domain"] or "",
        main_tasks=_json_list(row["main_tasks"]),
        required_skills=_json_list(row["required_skills"]),
        nice_to_have=_json_list(row["nice_to_have"]),
        match_reasons=_json_list(row["match_reasons"]),
        risks=_json_list(row["risks"]),
        cv_keywords_to_include=_json_list(row["cv_keywords_to_include"]),
    )


def _fmt_skills(cv: AdaptedCV) -> str:
    parts = []
    for block in cv.selected_skills:
        parts.append(f"{block.category_id}=[{', '.join(block.skills)}]")
    return "; ".join(parts)


def main() -> None:
    profile = get_profile()
    allowed_lower = {s.lower() for s in profile.skills.allowed_skills}

    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute(
        """
        SELECT
            a.job_id,
            j.title,
            j.company,
            a.cv_json,
            ja.role_type,
            ja.seniority,
            ja.domain,
            ja.main_tasks,
            ja.required_skills,
            ja.nice_to_have,
            ja.match_reasons,
            ja.risks,
            ja.cv_keywords_to_include
        FROM applications a
        JOIN jobs j ON a.job_id = j.id
        JOIN job_analyses ja ON ja.job_id = a.job_id
        ORDER BY a.id
        """
    )
    rows = cur.fetchall()

    summary = []
    print(f"{'#':<3} {'job_id':<6} {'family':<24} title — company")
    print("-" * 110)
    for idx, row in enumerate(rows, start=1):
        cv_json = json.loads(row["cv_json"])
        before_cv = _rebuild_cv(cv_json)
        analysis = _rebuild_analysis(row)
        job_title = row["title"] or ""
        family = classify(analysis, title=job_title)
        after_cv, _ = apply_contract(
            before_cv,
            analysis=analysis,
            job_title=job_title,
            allowed_skills_lower=allowed_lower,
        )

        before_set = {
            (block.category_id, skill)
            for block in before_cv.selected_skills
            for skill in block.skills
        }
        after_set = {
            (block.category_id, skill)
            for block in after_cv.selected_skills
            for skill in block.skills
        }
        added = sorted(s for s in (after_set - before_set))
        removed = sorted(s for s in (before_set - after_set))

        summary.append(
            {
                "idx": idx,
                "job_id": row["job_id"],
                "title": job_title,
                "company": row["company"],
                "family": family,
                "before": _fmt_skills(before_cv),
                "after": _fmt_skills(after_cv),
                "added": added,
                "removed": removed,
            }
        )
        print(
            f"{idx:<3} {row['job_id']:<6} {family:<24} {job_title[:55]} — {row['company'][:30]}"
        )
        if added:
            print(f"      + {', '.join(f'{c}:{s}' for c, s in added)}")
        if removed:
            print(f"      - {', '.join(f'{c}:{s}' for c, s in removed)}")
        if not added and not removed:
            print("      (no change)")

    # Compact summary at the end.
    n_changed = sum(1 for s in summary if s["added"] or s["removed"])
    print()
    print(f"Total jobs: {len(summary)}")
    print(f"Jobs with skill changes: {n_changed}")

    # Save full json for further analysis
    out_path = REPO_ROOT / "data" / "skill_contract_replay.json"
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
