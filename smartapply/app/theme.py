"""Shared Streamlit theme for the Smart Apply UI."""

from __future__ import annotations

import streamlit as st

APP_CSS = """
        <style>
        :root {
            --sa-bg: #262626;
            --sa-bg-2: #161616;
            --sa-surface: #393939;
            --sa-surface-raised: #393939;
            --sa-surface-2: #2B2B2B;
            --sa-surface-3: #525252;
            --sa-surface-hover: #454545;
            --sa-table-shell: #262626;
            --sa-table-header: #393939;
            --sa-table-row: #2B2B2B;
            --sa-text: #E0E0E0;
            --sa-muted: #B8B8B8;
            --sa-border: #525252;
            --sa-border-strong: #6F6F6F;
            --sa-primary: #78A9FF;
            --sa-primary-soft: #28384E;
            --sa-primary-subtle: #303D52;
            --sa-primary-strong: #A6C8FF;
            --sa-good: #A6C8FF;
            --sa-warn: #D2B36A;
            --sa-bad: #FFB3B8;
            --sa-brass: #D2B36A;
            --sa-brass-soft: #3D3524;
            --sa-ink: #D8D8D8;
            --sa-shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.26);
            --sa-shadow-md: 0 18px 42px rgba(0, 0, 0, 0.34);
        }
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"],
        [data-testid="stAppDeployButton"],
        [data-testid="stMainMenu"] {
            display: none !important;
        }
        [data-testid="stToolbar"] {
            display: flex !important;
        }
        [data-testid="stHeaderActionElements"] {
            display: flex !important;
        }
        [data-testid="stHeaderActionElements"] button,
        [data-testid="stHeaderActionElements"] button svg {
            color: var(--sa-text) !important;
        }
        [data-testid="stSidebarCollapseButton"],
        [data-testid="stExpandSidebarButton"],
        [data-testid="stSidebarCollapsedControl"] {
            display: flex !important;
            opacity: 1 !important;
            visibility: visible !important;
        }
        [data-testid="stSidebarCollapseButton"] button,
        [data-testid="stSidebarCollapseButton"] button *,
        [data-testid="stExpandSidebarButton"],
        [data-testid="stExpandSidebarButton"] *,
        [data-testid="stSidebarCollapsedControl"] button,
        [data-testid="stSidebarCollapsedControl"] button * {
            color: var(--sa-text) !important;
            opacity: 1 !important;
            visibility: visible !important;
        }
        .stApp,
        [data-testid="stAppViewContainer"] {
            background:
                linear-gradient(180deg, rgba(38, 38, 38, 0.98), rgba(31, 31, 31, 0.99)),
                linear-gradient(135deg, #262626 0%, #2B2B2B 58%, #1F1F1F 100%) !important;
            color: var(--sa-text) !important;
            font-family: 'Inter', -apple-system, sans-serif;
            font-size: 15.5px;
        }
        [data-testid="stHeader"] {
            background-color: rgba(38, 38, 38, 0.90) !important;
            backdrop-filter: blur(8px);
            min-height: 0 !important;
        }
        .main .block-container {
            max-width: 1360px;
            padding-top: 1.65rem;
            padding-bottom: 3rem;
        }
        div[data-testid="stVerticalBlock"] {
            gap: 0.85rem;
        }
        section[data-testid="stSidebar"] {
            background:
                linear-gradient(180deg, #2B2B2B 0%, #242424 100%) !important;
            color: var(--sa-text) !important;
            border-right: 1px solid var(--sa-border);
            box-shadow: inset -1px 0 0 rgba(255, 255, 255, 0.02);
        }
        section[data-testid="stSidebar"] > div,
        section[data-testid="stSidebar"] [data-testid="stSidebarContent"],
        section[data-testid="stSidebar"] [data-testid="stSidebarNav"] {
            background-color: var(--sa-surface-2) !important;
            color: var(--sa-text) !important;
        }
        section[data-testid="stSidebar"] * {
            color: var(--sa-text) !important;
        }
        section[data-testid="stSidebar"] a,
        section[data-testid="stSidebar"] a *,
        section[data-testid="stSidebar"] button,
        section[data-testid="stSidebar"] button *,
        section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"],
        section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"] * {
            color: var(--sa-text) !important;
            border-radius: 8px !important;
        }
        section[data-testid="stSidebar"] a:hover,
        section[data-testid="stSidebar"] button:hover {
            background-color: #333333 !important;
            color: var(--sa-text) !important;
        }
        section[data-testid="stSidebar"] [aria-current="page"],
        section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"][aria-current="page"] {
            background-color: var(--sa-primary-soft) !important;
            color: var(--sa-primary-strong) !important;
            font-weight: 700;
            box-shadow: inset 3px 0 0 var(--sa-primary);
        }
        section[data-testid="stSidebar"] [aria-current="page"] *,
        section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"][aria-current="page"] * {
            color: var(--sa-primary-strong) !important;
        }
        section[data-testid="stSidebar"] svg,
        section[data-testid="stSidebar"] svg path {
            fill: currentColor !important;
            color: var(--sa-text) !important;
        }
        h1, h2, h3 { color: var(--sa-ink) !important; letter-spacing: 0 !important; }
        h1 { font-size: clamp(1.82rem, 2.7vw, 2.35rem) !important; }
        h2 { font-size: clamp(1.48rem, 2.1vw, 1.92rem) !important; }
        h3 { font-size: clamp(1.17rem, 1.7vw, 1.42rem) !important; }
        p, li, label, span { letter-spacing: 0 !important; }
        [data-testid="stMarkdownContainer"],
        [data-testid="stText"],
        [data-testid="stMetricLabel"],
        [data-testid="stMetricValue"],
        [data-testid="stDataFrame"],
        [data-testid="stDataEditor"],
        .stTextInput input,
        .stTextArea textarea,
        .stSelectbox,
        .stMultiSelect,
        .stNumberInput input,
        .stDateInput input {
            font-size: 0.96rem !important;
        }
        .stButton > button,
        .stDownloadButton > button,
        [data-testid="stBaseButton-secondary"],
        [data-testid="stBaseButton-primary"] {
            border-radius: 8px !important;
            border: 1px solid var(--sa-border-strong) !important;
            font-size: 0.96rem !important;
            font-weight: 750 !important;
            min-height: 2.5rem;
            box-shadow: var(--sa-shadow-sm);
            transition: background-color 120ms ease, border-color 120ms ease, transform 120ms ease, box-shadow 120ms ease;
        }
        [data-testid="stBaseButton-secondary"],
        .stButton > button:not([data-testid="stBaseButton-primary"]),
        .stDownloadButton > button {
            background: #303030 !important;
            color: var(--sa-text) !important;
        }
        .stButton > button:hover,
        .stDownloadButton > button:hover {
            border-color: var(--sa-primary) !important;
            background: #383838 !important;
            transform: translateY(-1px);
            box-shadow: 0 10px 22px rgba(0, 0, 0, 0.26);
        }
        .main a[data-testid="stPageLink"] {
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 2.5rem;
            border: 1px solid var(--sa-border-strong);
            border-radius: 8px;
            background: var(--sa-surface-raised);
            color: var(--sa-ink) !important;
            font-weight: 750;
            text-decoration: none !important;
            box-shadow: var(--sa-shadow-sm);
            transition: background-color 120ms ease, border-color 120ms ease, transform 120ms ease;
        }
        .main a[data-testid="stPageLink"]:hover {
            border-color: var(--sa-primary);
            background: var(--sa-surface-hover);
            transform: translateY(-1px);
        }
        .main a[data-testid="stPageLink"] * {
            color: inherit !important;
            text-decoration: none !important;
        }
        [data-testid="stBaseButton-primary"] {
            background: var(--sa-primary) !important;
            border-color: var(--sa-primary) !important;
            color: #161616 !important;
            box-shadow: 0 10px 24px rgba(120, 169, 255, 0.16);
        }
        [data-testid="stBaseButton-primary"] * {
            color: #161616 !important;
        }
        input,
        textarea,
        [data-baseweb="select"] > div,
        [data-baseweb="tag"] {
            border-radius: 8px !important;
            background-color: #303030 !important;
            border-color: #4A4A4A !important;
            color: var(--sa-text) !important;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.02);
        }
        input::placeholder,
        textarea::placeholder {
            color: #8D8D8D !important;
        }
        [data-baseweb="tab-list"] {
            gap: 0.35rem;
            border-bottom: 1px solid var(--sa-border);
        }
        [data-baseweb="tab"] {
            border-radius: 8px 8px 0 0;
            padding: 0.55rem 0.8rem;
            font-weight: 750;
        }
        [data-baseweb="tab"][aria-selected="true"] {
            background: var(--sa-primary-subtle);
            color: var(--sa-primary-strong);
        }
        [data-testid="stExpander"] {
            border: 1px solid var(--sa-border) !important;
            border-radius: 8px !important;
            background: var(--sa-surface-raised) !important;
            box-shadow: var(--sa-shadow-sm);
        }
        [data-testid="stExpander"] summary {
            font-weight: 800;
            color: var(--sa-ink);
        }
        [data-testid="stMetric"],
        .stMetric {
            background-color: var(--sa-surface) !important;
            color: var(--sa-text) !important;
            padding: 0.95rem;
            border-radius: 8px;
            border: 1px solid var(--sa-border);
            box-shadow: var(--sa-shadow-sm);
        }
        [data-testid="stMetric"]:hover,
        .stMetric:hover {
            border-color: var(--sa-border-strong);
            background-color: #3F3F3F !important;
        }
        [data-testid="stMetric"] *,
        .stMetric * {
            color: var(--sa-text) !important;
        }
        div[data-testid="stDataFrame"],
        div[data-testid="stDataEditor"] {
            border: 1px solid #5A5A5A;
            border-radius: 8px;
            overflow: hidden;
            background: var(--sa-table-shell) !important;
            box-shadow: 0 18px 40px rgba(0, 0, 0, 0.28);
        }
        div[data-testid="stDataFrame"] [role="grid"],
        div[data-testid="stDataEditor"] [role="grid"],
        div[data-testid="stDataFrame"] [data-testid="stDataFrameResizable"],
        div[data-testid="stDataEditor"] [data-testid="stDataFrameResizable"] {
            background: var(--sa-table-shell) !important;
        }
        div[data-testid="stDataFrame"] [role="columnheader"],
        div[data-testid="stDataEditor"] [role="columnheader"] {
            background: var(--sa-table-header) !important;
            color: var(--sa-ink) !important;
            font-weight: 800 !important;
        }
        div[data-testid="stDataFrame"] canvas,
        div[data-testid="stDataEditor"] canvas {
            background-color: var(--sa-table-row) !important;
        }
        div[data-testid="stVegaLiteChart"] [data-testid="stElementToolbar"],
        div[data-testid="stAltairChart"] [data-testid="stElementToolbar"] {
            display: none !important;
        }
        .sa-hero {
            position: relative;
            background:
                linear-gradient(180deg, rgba(57, 57, 57, 0.96), rgba(48, 48, 48, 0.98)),
                linear-gradient(135deg, #393939, #2B2B2B 58%, #262626);
            border: 1px solid var(--sa-border);
            border-radius: 8px;
            padding: 1.35rem 1.45rem;
            box-shadow: var(--sa-shadow-md);
            margin-bottom: 0.85rem;
            overflow: hidden;
        }
        .sa-hero::before {
            content: "";
            position: absolute;
            inset: 0 0 auto 0;
            height: 4px;
            background: linear-gradient(90deg, var(--sa-primary), #A8A8A8);
        }
        .sa-hero h1, .sa-hero h2, .sa-hero h3 {
            margin: 0 0 0.25rem 0 !important;
        }
        .sa-muted {
            color: var(--sa-muted);
            font-size: 0.92rem;
        }
        .sa-panel {
            background: var(--sa-surface-raised);
            border: 1px solid var(--sa-border);
            border-radius: 8px;
            padding: 1.15rem 1.2rem;
            box-shadow: var(--sa-shadow-sm);
            margin-bottom: 0.85rem;
        }
        .sa-panel:hover {
            border-color: #5C5C5C;
        }
        .sa-panel-quiet {
            background: var(--sa-surface-2);
            border: 1px solid var(--sa-border);
            border-radius: 8px;
            padding: 0.9rem 1rem;
        }
        .sa-toolbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
            flex-wrap: wrap;
            background: var(--sa-surface);
            border: 1px solid var(--sa-border);
            border-radius: 8px;
            padding: 0.75rem 0.9rem;
            margin: 0.65rem 0;
        }
        .sa-section-header {
            display: flex;
            align-items: flex-end;
            justify-content: space-between;
            gap: 1rem;
            flex-wrap: wrap;
            margin: 1rem 0 0.45rem 0;
        }
        .sa-section-header h3 {
            margin: 0 !important;
            font-size: 1.02rem !important;
            line-height: 1.2;
        }
        .sa-section-subtitle {
            color: var(--sa-muted);
            font-size: 0.9rem;
            margin-top: 0.15rem;
        }
        .sa-focus-band {
            display: grid;
            grid-template-columns: minmax(0, 1fr) auto;
            gap: 1rem;
            align-items: center;
            background:
                linear-gradient(180deg, rgba(57,57,57,0.96), rgba(43,43,43,1)),
                linear-gradient(135deg, var(--sa-primary-soft), var(--sa-surface-2));
            border: 1px solid var(--sa-border);
            border-left: 5px solid var(--sa-primary);
            border-radius: 8px;
            padding: 1rem 1.1rem;
            box-shadow: var(--sa-shadow-sm);
            margin: 0.75rem 0;
        }
        .sa-focus-kicker {
            color: var(--sa-primary-strong);
            font-size: 0.78rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0 !important;
        }
        .sa-focus-title {
            color: var(--sa-ink);
            font-size: 1.2rem;
            font-weight: 850;
            margin-top: 0.15rem;
        }
        .sa-focus-copy {
            color: var(--sa-muted);
            font-size: 0.93rem;
            line-height: 1.45;
            margin-top: 0.2rem;
        }
        .sa-action-strip {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            flex-wrap: wrap;
            background: var(--sa-surface-raised);
            border: 1px solid var(--sa-border);
            border-radius: 8px;
            padding: 0.85rem 1rem;
            box-shadow: var(--sa-shadow-sm);
            margin: 0.75rem 0;
        }
        .sa-home-layout {
            display: grid;
            grid-template-columns: minmax(0, 1.55fr) minmax(280px, 0.8fr);
            gap: 1rem;
            margin-bottom: 1rem;
        }
        .sa-home-hero {
            background:
                linear-gradient(180deg, rgba(57,57,57,0.97), rgba(48,48,48,1)),
                linear-gradient(135deg, #393939 0%, #2B2B2B 56%, #262626 100%);
            border: 1px solid var(--sa-border);
            border-radius: 8px;
            padding: 1.35rem 1.5rem;
            box-shadow: var(--sa-shadow-md);
            min-height: 190px;
            position: relative;
            overflow: hidden;
        }
        .sa-home-hero::before {
            content: "";
            position: absolute;
            inset: 0 0 auto 0;
            height: 5px;
            background: linear-gradient(90deg, var(--sa-primary), #A8A8A8);
        }
        .sa-home-eyebrow {
            display: inline-flex;
            align-items: center;
            border: 1px solid var(--sa-border-strong);
            background: var(--sa-primary-soft);
            color: var(--sa-primary-strong);
            border-radius: 999px;
            padding: 0.22rem 0.58rem;
            font-size: 0.76rem;
            font-weight: 850;
            margin-bottom: 0.85rem;
        }
        .sa-home-title {
            color: var(--sa-ink);
            font-size: clamp(1.7rem, 3vw, 2.35rem);
            line-height: 1.02;
            font-weight: 850;
            margin: 0 0 0.7rem 0;
        }
        .sa-home-copy {
            color: var(--sa-muted);
            max-width: 720px;
            line-height: 1.55;
            font-size: 1rem;
        }
        .sa-home-panel {
            background: var(--sa-surface-raised);
            border: 1px solid var(--sa-border);
            border-radius: 8px;
            padding: 1.1rem;
            box-shadow: var(--sa-shadow-md);
            position: relative;
            overflow: hidden;
        }
        .sa-home-panel::before {
            content: "";
            position: absolute;
            inset: 0 auto 0 0;
            width: 3px;
            background: var(--sa-primary);
        }
        .sa-home-next-title {
            color: var(--sa-ink);
            font-size: 1.08rem;
            font-weight: 820;
            line-height: 1.15;
            margin: 0.35rem 0;
        }
        .sa-home-next-copy {
            color: var(--sa-muted);
            font-size: 0.92rem;
            line-height: 1.45;
        }
        .sa-custom-metrics {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
            gap: 0.75rem;
            margin: 0.85rem 0 1rem 0;
        }
        .sa-custom-metric {
            background: var(--sa-surface-raised);
            border: 1px solid var(--sa-border);
            border-radius: 8px;
            padding: 0.9rem 0.95rem;
            box-shadow: var(--sa-shadow-sm);
            position: relative;
            overflow: hidden;
        }
        .sa-custom-metric:hover {
            border-color: #5C5C5C;
            background: #3F3F3F;
        }
        .sa-custom-metric::before {
            content: "";
            position: absolute;
            inset: 0 auto 0 0;
            width: 4px;
            background: var(--metric-accent, var(--sa-primary));
        }
        .sa-custom-metric-label {
            color: var(--sa-muted);
            font-size: 0.78rem;
            font-weight: 800;
            text-transform: uppercase;
        }
        .sa-custom-metric-value {
            color: var(--sa-ink);
            font-size: 1.7rem;
            font-weight: 840;
            line-height: 1;
            margin-top: 0.32rem;
        }
        .sa-custom-metric-note {
            color: var(--sa-muted);
            font-size: 0.82rem;
            margin-top: 0.35rem;
        }
        .sa-nav-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
            gap: 0.9rem;
            margin: 0.75rem 0 1.2rem 0;
        }
        .sa-nav-card {
            background: var(--sa-surface-raised);
            border: 1px solid var(--sa-border);
            border-radius: 8px;
            padding: 1rem;
            min-height: 142px;
            box-shadow: var(--sa-shadow-sm);
            display: grid;
            gap: 0.55rem;
        }
        .sa-nav-card:hover {
            border-color: var(--sa-primary);
            background: #3F3F3F;
            box-shadow: var(--sa-shadow-md);
        }
        .sa-nav-top {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
        }
        .sa-nav-icon {
            width: 2.35rem;
            height: 2.35rem;
            border-radius: 8px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: var(--nav-soft, var(--sa-primary-soft));
            color: var(--nav-accent, var(--sa-primary));
            font-weight: 900;
            font-size: 1.05rem;
        }
        .sa-nav-card h4 {
            margin: 0;
            color: var(--sa-ink);
            font-size: 1.02rem;
        }
        .sa-nav-card p {
            margin: 0;
            color: var(--sa-muted);
            font-size: 0.9rem;
            line-height: 1.42;
        }
        .sa-action-strip strong {
            color: var(--sa-ink);
        }
        .sa-stat-row {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
            gap: 0.75rem;
            margin: 0.85rem 0;
        }
        .sa-stat-card {
            background: var(--sa-surface-raised);
            border: 1px solid var(--sa-border);
            border-radius: 8px;
            padding: 0.85rem 0.95rem;
            box-shadow: var(--sa-shadow-sm);
        }
        .sa-stat-card:hover {
            background: #3F3F3F;
            border-color: #5C5C5C;
        }
        .sa-stat-label {
            color: var(--sa-muted);
            font-size: 0.78rem;
            font-weight: 750;
            text-transform: uppercase;
        }
        .sa-stat-value {
            color: var(--sa-ink);
            font-size: 1.45rem;
            font-weight: 850;
            line-height: 1.15;
            margin-top: 0.2rem;
        }
        .sa-stat-note {
            color: var(--sa-muted);
            font-size: 0.82rem;
            margin-top: 0.1rem;
        }
        .sa-step {
            display: flex;
            gap: 0.65rem;
            align-items: center;
            background: var(--sa-surface-raised);
            border: 1px solid var(--sa-border);
            border-radius: 8px;
            padding: 0.65rem 0.75rem;
            min-height: 74px;
            box-shadow: var(--sa-shadow-sm);
            transition: border-color 120ms ease, background-color 120ms ease, transform 120ms ease;
        }
        .sa-step:hover {
            transform: translateY(-1px);
            border-color: var(--sa-primary);
        }
        .sa-step-active {
            border-color: var(--sa-primary);
            background: var(--sa-primary-subtle);
            box-shadow: 0 10px 22px rgba(120, 169, 255, 0.12);
        }
        .sa-step-done {
            border-color: #525252;
            background: #393939;
        }
        .sa-step-num {
            width: 2rem;
            height: 2rem;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-radius: 999px;
            background: var(--sa-primary-soft);
            color: var(--sa-primary);
            font-weight: 800;
            flex-shrink: 0;
        }
        .sa-step-title {
            font-weight: 800;
            color: var(--sa-ink);
            line-height: 1.2;
        }
        .sa-step-caption {
            color: var(--sa-muted);
            font-size: 0.82rem;
            line-height: 1.25;
        }
        .sa-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            border: 1px solid var(--sa-border);
            border-radius: 999px;
            padding: 0.18rem 0.55rem;
            font-size: 0.78rem;
            font-weight: 700;
            color: var(--sa-muted);
            background: var(--sa-surface-2);
            white-space: nowrap;
        }
        .sa-pill-good { color: #D0E2FF; background: #28384E; border-color: #4D5F7A; }
        .sa-pill-warn { color: #E0C47C; background: #3A321F; border-color: #6E5B30; }
        .sa-pill-bad { color: #F0B0AA; background: #3A2425; border-color: #704443; }
        .sa-pill-blue { color: var(--sa-primary-strong); background: var(--sa-primary-soft); border-color: #4D5F7A; }
        .sa-pill-neutral { color: #D0D0D0; background: #393939; border-color: #525252; }
        .sa-pill-purple { color: #C6C6C6; background: #393939; border-color: #525252; }
        .sa-pill-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.35rem;
            align-items: center;
            margin: 0.45rem 0 0.1rem 0;
        }
        .sa-kv {
            display: grid;
            grid-template-columns: 8.5rem 1fr;
            gap: 0.35rem 0.75rem;
            font-size: 0.92rem;
        }
        .sa-kv-label { color: var(--sa-muted); }
        .sa-kv-value { color: var(--sa-text); font-weight: 650; }
        .sa-box-title {
            margin: 0 0 0.25rem 0;
            color: var(--sa-ink);
            font-weight: 800;
            font-size: 0.98rem;
        }
        .sa-box-message {
            color: var(--sa-muted);
            font-size: 0.9rem;
            line-height: 1.42;
        }
        .sa-runbar {
            border: 1px solid #4D5F7A;
            background: var(--sa-primary-soft);
            color: var(--sa-primary-strong);
            border-radius: 8px;
            padding: 0.75rem 0.9rem;
            margin: 0.75rem 0;
        }
        .sa-danger {
            border-color: #704443;
            background: #3A2425;
            color: #F0B0AA;
        }
        .sa-warning {
            border-color: #6E5B30;
            background: #3A321F;
            color: #E0C47C;
        }
        .sa-success {
            border-color: #4D5F7A;
            background: #28384E;
            color: #D0E2FF;
        }
        .sa-command-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
            gap: 0.85rem;
            margin: 0.85rem 0;
        }
        .sa-action-card {
            background: var(--sa-surface-raised);
            border: 1px solid var(--sa-border);
            border-radius: 8px;
            padding: 1rem;
            min-height: 138px;
            box-shadow: var(--sa-shadow-sm);
        }
        .sa-action-card:hover {
            border-color: var(--sa-primary);
            box-shadow: var(--sa-shadow-md);
        }
        .sa-action-card h4 {
            margin: 0 0 0.35rem 0;
            color: var(--sa-ink);
            font-size: 1rem;
        }
        .sa-action-card p {
            margin: 0;
            color: var(--sa-muted);
            font-size: 0.9rem;
            line-height: 1.35;
        }
        .sa-inline-actions {
            display: flex;
            gap: 0.55rem;
            flex-wrap: wrap;
            align-items: center;
        }
        .sa-table-note {
            color: var(--sa-muted);
            font-size: 0.82rem;
            margin-top: -0.35rem;
        }
        @media (max-width: 760px) {
            .main .block-container {
                padding-left: 0.8rem;
                padding-right: 0.8rem;
            }
            .sa-home-layout {
                grid-template-columns: 1fr;
            }
            .sa-focus-band {
                grid-template-columns: 1fr;
            }
            .sa-step {
                min-height: 64px;
            }
        }
        </style>
"""


def render_app_style() -> None:
    """Render the global application stylesheet once per Streamlit rerun."""
    st.markdown(APP_CSS, unsafe_allow_html=True)
