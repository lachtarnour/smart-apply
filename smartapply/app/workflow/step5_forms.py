"""Form-question assistant helpers for workflow step 5."""

from __future__ import annotations

from typing import Any

import streamlit as st

from smartapply.app._helpers import pipeline_singleton
from smartapply.database import session_scope
from smartapply.database.repository import upsert_document
from smartapply.llm import FormQuestionAnswers, LLMError
from smartapply.llm.prompts.form_questions import build_form_questions_prompt
from smartapply.pipeline.output_paths import application_output_dir


def _render_form_questions_assistant(row: dict[str, Any]) -> None:
    app_id = int(row["id"])
    questions_key = f"wf_form_questions_{app_id}"
    result_key = f"wf_form_question_answers_{app_id}"
    st.session_state.setdefault(questions_key, "")

    with st.popover(
        "Questions formulaire",
        key=f"wf_form_questions_popover_{app_id}",
        width="stretch",
        help="Colle les questions du formulaire ATS pour générer des réponses ancrées dans le profil et l'offre.",
    ):
        st.text_area(
            "Questions du formulaire",
            key=questions_key,
            height=180,
            placeholder=(
                "Ex:\n"
                "What makes Joko special according to you?\n\n"
                "Why do you think your qualities and your profile are relevant for this role?"
            ),
        )
        st.caption(
            "Tu peux coller plusieurs questions : un seul clic envoie l'offre, ton profil complet et "
            "toutes les questions au LLM."
        )
        col_generate, col_clear = st.columns(2)
        with col_generate:
            if st.button(
                "Générer les réponses",
                key=f"wf_generate_form_answers_{app_id}",
                type="primary",
                width="stretch",
            ):
                questions = str(st.session_state.get(questions_key) or "").strip()
                if not questions:
                    st.error("Colle au moins une question du formulaire.")
                else:
                    with st.spinner("Appel LLM en cours..."):
                        generated = _generate_form_question_answers(row, questions)
                    if generated is not None:
                        st.session_state[result_key] = generated.model_dump()
                        _clear_form_answer_widget_state(app_id)
        with col_clear:
            st.button(
                "Effacer",
                key=f"wf_clear_form_answers_{app_id}",
                width="stretch",
                on_click=_clear_form_questions_state,
                args=(app_id, questions_key, result_key),
            )

        result = st.session_state.get(result_key)
        if isinstance(result, dict):
            _render_form_question_answers(app_id, result)


def _generate_form_question_answers(
    row: dict[str, Any],
    questions: str,
) -> FormQuestionAnswers | None:
    pipeline = pipeline_singleton()
    system, user = build_form_questions_prompt(
        profile=pipeline.profile,
        row=row,
        questions=questions,
    )
    try:
        answers = pipeline.llm.complete_json(
            system=system,
            user=user,
            schema=FormQuestionAnswers,
            model=pipeline.llm.cheap_model,
            temperature=0.2,
            purpose="form_questions",
            job_id=int(row["job_id"]) if row.get("job_id") is not None else None,
            use_cache=True,
        )
    except LLMError as exc:
        st.error(f"Appel LLM impossible : {exc}")
        return None

    _persist_form_question_answers(row, questions, answers)
    st.success("Réponses générées.")
    return answers


def _render_form_question_answers(app_id: int, result: dict[str, Any]) -> None:
    warnings = result.get("global_warnings")
    if isinstance(warnings, list) and warnings:
        st.warning(" · ".join(str(warning) for warning in warnings[:4]))

    answers = result.get("answers")
    if not isinstance(answers, list) or not answers:
        st.info("Aucune réponse générée.")
        return

    for index, item in enumerate(answers, start=1):
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or f"Question {index}").strip()
        answer = str(item.get("answer") or "").strip()
        st.markdown(f"**{index}. {question}**")
        st.text_area(
            "Réponse générée",
            value=answer,
            height=180,
            key=f"wf_form_answer_{app_id}_{index}",
            label_visibility="collapsed",
        )
        evidence = item.get("evidence_used")
        if isinstance(evidence, list) and evidence:
            st.caption("Preuves : " + " · ".join(str(value) for value in evidence[:5]))
        item_warnings = item.get("warnings")
        if isinstance(item_warnings, list) and item_warnings:
            st.caption("À vérifier : " + " · ".join(str(value) for value in item_warnings[:3]))


def _clear_form_answer_widget_state(app_id: int) -> None:
    prefix = f"wf_form_answer_{app_id}_"
    for key in list(st.session_state.keys()):
        if str(key).startswith(prefix):
            st.session_state.pop(key, None)


def _clear_form_questions_state(app_id: int, questions_key: str, result_key: str) -> None:
    st.session_state.pop(result_key, None)
    st.session_state[questions_key] = ""
    _clear_form_answer_widget_state(app_id)


def _persist_form_question_answers(
    row: dict[str, Any],
    questions: str,
    answers: FormQuestionAnswers,
) -> None:
    app_id = int(row["id"])
    output_dir = application_output_dir(pipeline_singleton().settings.output_dir, app_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    text_path = output_dir / "form_question_answers.txt"
    text_path.write_text(
        _format_form_question_answers_text(questions, answers),
        encoding="utf-8",
    )
    with session_scope() as s:
        upsert_document(
            s,
            app_id,
            doc_type="form_question_answers",
            path=str(text_path),
            content=answers.model_dump_json(indent=2),
            extra={"questions": questions},
        )


def _format_form_question_answers_text(
    questions: str,
    answers: FormQuestionAnswers,
) -> str:
    lines = [
        "Questions formulaire",
        "",
        "Questions source:",
        questions.strip(),
        "",
        "Réponses générées:",
    ]
    for index, item in enumerate(answers.answers, start=1):
        lines.extend(
            [
                "",
                f"{index}. {item.question}",
                item.answer,
            ]
        )
        if item.evidence_used:
            lines.append("Preuves: " + " ; ".join(item.evidence_used))
        if item.warnings:
            lines.append("À vérifier: " + " ; ".join(item.warnings))
    if answers.global_warnings:
        lines.extend(["", "Warnings globaux:", " ; ".join(answers.global_warnings)])
    return "\n".join(lines).strip() + "\n"
