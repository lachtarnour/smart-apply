"""Profile viewer — read-only display of the candidate profile."""

from __future__ import annotations

import streamlit as st

from smartapply.app._helpers import (
    apply_app_style,
    render_badge_row,
    render_info_panel,
    render_page_header,
)
from smartapply.profile import get_profile

st.set_page_config(page_title="Profil | SmartApply", page_icon="👤", layout="wide")
apply_app_style()

profile = get_profile()

render_page_header(
    "Profil",
    "Source de vérité utilisée par la génération de CV, lettres et emails.",
    icon="👤",
    badges=[
        ("Lecture seule", "neutral"),
        ("Source anti-hallucination", "good"),
        ("Données brutes disponibles", "blue"),
    ],
)

render_info_panel(
    "Pourquoi les source_id existent",
    "Chaque expérience, projet et bullet possède un identifiant stable. Le validateur les utilise pour empêcher les affirmations inventées dans les documents générés.",
)

# ---- Identity ----
left, right = st.columns([1.35, 1])
with left:
    st.markdown(
        f"""
        <div class="sa-panel">
          <h3 style="margin:0;">{profile.identity.full_name}</h3>
          <div class="sa-muted">{profile.identity.title} · {profile.identity.location}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.write(profile.identity.summary)
with right:
    st.markdown("### Contact")
    st.markdown(
        f"""
        <div class="sa-kv">
          <div class="sa-kv-label">Email</div><div class="sa-kv-value">{profile.identity.email}</div>
          <div class="sa-kv-label">Téléphone</div><div class="sa-kv-value">{profile.identity.phone or '—'}</div>
          <div class="sa-kv-label">GitHub</div><div class="sa-kv-value">{profile.identity.github or '—'}</div>
          <div class="sa-kv-label">LinkedIn</div><div class="sa-kv-value">{profile.identity.linkedin or '—'}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ---- Preferences ----
st.markdown("### Préférences de recherche")
pref = profile.preferences
p1, p2 = st.columns(2)
with p1:
    st.caption("Rôles ciblés")
    render_badge_row([(role, "blue") for role in pref.target_roles])
    st.caption("Localisations")
    render_badge_row([(location, "good") for location in pref.preferred_locations])
with p2:
    st.caption("Contrats acceptés")
    render_badge_row([(contract, "purple") for contract in pref.accepted_contract_types])
    st.caption("Remote et langues")
    render_badge_row(
        [(policy, "neutral") for policy in pref.accepted_remote_policies]
        + [(lang, "blue") for lang in pref.accepted_job_languages]
    )
if pref.domains_of_interest:
    st.caption("Domaines d'intérêt")
    render_badge_row([(domain, "good") for domain in pref.domains_of_interest])
if pref.deal_breakers:
    st.caption("Deal breakers")
    render_badge_row([(breaker, "warn") for breaker in pref.deal_breakers])

with st.expander("Données brutes des préférences"):
    st.json(pref.model_dump())

# ---- Skills ----
st.markdown("### Compétences")
for category in profile.skills.categories:
    with st.container():
        st.markdown(f"**{category.name}**")
        render_badge_row([(skill, "blue") for skill in category.skills])

with st.expander("Profils de compétences CV"):
    for skill_profile in profile.skills.profiles:
        st.markdown(f"**{skill_profile.name}** · `{skill_profile.id}`")
        if skill_profile.description:
            st.caption(skill_profile.description)
        for category_id, skills in skill_profile.category_skills.items():
            st.caption(category_id)
            render_badge_row([(skill, "neutral") for skill in skills])

# ---- Experiences ----
st.markdown("### Expériences professionnelles")
for exp in profile.experiences:
    with st.expander(
        f"{exp.title} — {exp.company} ({exp.start_date} → {exp.end_date})",
        expanded=False,
    ):
        render_badge_row([(exp.location, "neutral"), (f"source_id: {exp.id}", "neutral")])
        if exp.keywords:
            render_badge_row([(kw, "blue") for kw in exp.keywords])
        for blt in exp.bullets:
            st.markdown(f"- {blt.text}")
            details = [f"source_id: {blt.id}"]
            if blt.evidence_level:
                details.append(f"preuve: {blt.evidence_level}")
            if blt.numbers:
                details.append(f"chiffres: {', '.join(blt.numbers)}")
            st.caption(" · ".join(details))

# ---- Projects ----
st.markdown("### Projets")
for proj in profile.projects:
    with st.container():
        st.markdown(f"**{proj.name}**")
        render_badge_row([(proj.status or "statut non indiqué", "neutral"), (f"source_id: {proj.id}", "neutral")])
        if proj.keywords:
            render_badge_row([(kw, "blue") for kw in proj.keywords])
        for blt in proj.bullets:
            st.markdown(f"- {blt.text}")
            st.caption(f"source_id: {blt.id}")

# ---- Education / languages / certificates ----
edu_col, lang_col, cert_col = st.columns(3)
with edu_col:
    st.markdown("### Formation")
    for deg in profile.education:
        with st.container():
            st.markdown(f"**{deg.title}**")
            st.caption(f"{deg.field or ''} · {deg.institution}")
            render_badge_row([(f"{deg.start_year}–{deg.end_year}", "neutral"), (f"source_id: {deg.id}", "neutral")])

with lang_col:
    st.markdown("### Langues")
    for lang in profile.languages:
        with st.container():
            st.markdown(f"**{lang.name}**")
            st.caption(lang.level)

with cert_col:
    st.markdown("### Certifications")
    for cert in profile.certificates:
        with st.container():
            st.markdown(f"**{cert.name}**")
            st.caption(f"{cert.issuer} · {cert.date or 'date non indiquée'}")
            if cert.description:
                st.write(cert.description)
            st.caption(f"source_id: {cert.id}")

with st.expander("Données brutes du profil complet"):
    st.json(profile.model_dump(mode="json"))
