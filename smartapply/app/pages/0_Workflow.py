"""Interactive workflow: Fetch -> Score -> Analyze -> Generate -> Draft."""

from __future__ import annotations

import streamlit as st

from smartapply.app._helpers import apply_app_style
from smartapply.app.workflow import (
    init_workflow_state,
    render_stepper,
    step1_fetch,
    step2_score,
    step3_analyze,
    step4_generate,
    step5_send,
)

st.set_page_config(
    page_title="Workflow | SmartApply",
    page_icon="🧭",
    layout="wide",
)
apply_app_style()
init_workflow_state()

render_stepper()
st.divider()

step = st.session_state["wf_step"]
if step == 1:
    step1_fetch()
elif step == 2:
    step2_score()
elif step == 3:
    step3_analyze()
elif step == 4:
    step4_generate()
elif step == 5:
    step5_send()
