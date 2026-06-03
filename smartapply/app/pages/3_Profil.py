"""Profile viewer — read-only display of the candidate profile."""

from __future__ import annotations

import streamlit as st

from smartapply.app._helpers import apply_app_style
from smartapply.profile import get_profile


st.set_page_config(page_title="Profil | SmartApply", page_icon="👤", layout="wide")
apply_app_style()

st.title("👤 Profil candidat")
st.caption(
    "Source de vérité utilisée pour l'adaptation du CV. Les bullets ont un "
    "`source_id` stable — le validateur anti-hallucination s'en sert pour "
    "rejeter toute affirmation inventée par le LLM."
)

profile = get_profile()

# ---- Identity ----
st.subheader("Identité")
col1, col2 = st.columns(2)
col1.write(f"**Nom** : {profile.identity.full_name}")
col1.write(f"**Titre** : {profile.identity.title}")
col1.write(f"**Localisation** : {profile.identity.location}")
col2.write(f"**Email** : {profile.identity.email}")
if profile.identity.phone:
    col2.write(f"**Téléphone** : {profile.identity.phone}")
if profile.identity.github:
    col2.write(f"**GitHub** : {profile.identity.github}")
st.info(profile.identity.summary)

# ---- Preferences ----
with st.expander("Préférences de poste", expanded=False):
    st.json(profile.preferences.model_dump())

# ---- Skills ----
st.subheader("Compétences")
for category in profile.skills.categories:
    st.markdown(f"**{category.name}**")
    st.write(", ".join(category.skills))

# ---- Experiences ----
st.subheader("Expériences professionnelles")
for exp in profile.experiences:
    with st.expander(f"{exp.title} — {exp.company} ({exp.start_date} → {exp.end_date})"):
        st.caption(f"📍 {exp.location} · id=`{exp.id}`")
        for blt in exp.bullets:
            st.markdown(f"- *id=`{blt.id}`* — {blt.text}")
            if blt.numbers:
                st.caption(f"Chiffres validés : {', '.join(blt.numbers)}")

# ---- Projects ----
st.subheader("Projets")
for proj in profile.projects:
    st.markdown(f"- **{proj.name}** ({proj.status or '—'}) — *id=`{proj.id}`*")
    st.caption(proj.description)

# ---- Education ----
st.subheader("Formation")
for deg in profile.education:
    st.markdown(f"**{deg.title}** — {deg.field or ''}")
    st.caption(f"{deg.institution} · {deg.start_year}–{deg.end_year}")

# ---- Languages + Certificates ----
col_l, col_c = st.columns(2)
with col_l:
    st.subheader("Langues")
    for lang in profile.languages:
        st.write(f"- **{lang.name}** : {lang.level}")
with col_c:
    st.subheader("Certifications")
    for cert in profile.certificates:
        st.write(f"- **{cert.name}** ({cert.issuer})")
        if cert.description:
            st.caption(cert.description)
