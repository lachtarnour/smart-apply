"""Shared Streamlit theme for the Smart Apply UI."""

from __future__ import annotations

import streamlit as st

APP_CSS = """
        <style>
        :root {
            --sa-bg: #F8FAFC;
            --sa-bg-2: #EEF4FA;
            --sa-surface: #FFFFFF;
            --sa-surface-raised: #FFFFFF;
            --sa-surface-2: #F8FAFC;
            --sa-surface-3: #E8EEF7;
            --sa-surface-hover: #F3F7FC;
            --sa-table-shell: #FFFFFF;
            --sa-table-header: #F6F8FC;
            --sa-table-row: #FFFFFF;
            --sa-text: #182230;
            --sa-muted: #667085;
            --sa-border: #D9E2EC;
            --sa-border-strong: #B8C5D6;
            --sa-primary: #2563EB;
            --sa-primary-soft: #EAF2FF;
            --sa-primary-subtle: #DDEBFF;
            --sa-primary-strong: #1D4ED8;
            --sa-teal: #0F766E;
            --sa-teal-soft: #E6F6F4;
            --sa-violet: #7C3AED;
            --sa-violet-soft: #F2EDFF;
            --sa-good: #067647;
            --sa-warn: #B54708;
            --sa-bad: #B42318;
            --sa-brass: #B54708;
            --sa-brass-soft: #FFF4D6;
            --sa-ink: #101828;
            --sa-shadow-xs: 0 1px 2px rgba(16, 24, 40, 0.04);
            --sa-shadow-sm: 0 6px 18px rgba(16, 24, 40, 0.06);
            --sa-shadow-md: 0 16px 42px rgba(16, 24, 40, 0.08);
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
                linear-gradient(180deg, #FFFFFF 0, #F4F7FB 22rem, var(--sa-bg) 44rem)
                !important;
            color: var(--sa-text) !important;
            font-family: 'Inter', -apple-system, sans-serif;
            font-size: 15.5px;
        }
        [data-testid="stHeader"] {
            background-color: rgba(248, 250, 252, 0.82) !important;
            backdrop-filter: blur(12px);
            border-bottom: 1px solid rgba(217, 226, 236, 0.68);
            min-height: 0 !important;
        }
        [data-testid="stMainBlockContainer"],
        .stMainBlockContainer,
        .main .block-container {
            max-width: 1280px;
            padding-top: 2.6rem !important;
            padding-bottom: 5rem !important;
            padding-left: 2rem !important;
            padding-right: 2rem !important;
        }
        div[data-testid="stVerticalBlock"] {
            gap: 1.28rem;
        }
        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #FFFFFF 0%, #F8FAFC 100%) !important;
            color: var(--sa-text) !important;
            border-right: 1px solid var(--sa-border);
            box-shadow: 1px 0 0 rgba(16, 24, 40, 0.02), 14px 0 32px rgba(16, 24, 40, 0.035);
        }
        section[data-testid="stSidebar"] [data-testid="stSidebarNav"] {
            display: none !important;
        }
        section[data-testid="stSidebar"] > div,
        section[data-testid="stSidebar"] [data-testid="stSidebarContent"],
        section[data-testid="stSidebar"] [data-testid="stSidebarNav"] {
            background-color: #FFFFFF !important;
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
        section[data-testid="stSidebar"] a {
            min-height: 2.45rem;
            padding: 0.35rem 0.55rem !important;
            margin: 0.08rem 0 !important;
        }
        section[data-testid="stSidebar"] a:hover,
        section[data-testid="stSidebar"] button:hover {
            background-color: var(--sa-surface-hover) !important;
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
        .sa-sidebar-brand {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            padding: 0.72rem 0.72rem;
            margin: 0.1rem 0 0.95rem 0;
            border-bottom: 1px solid var(--sa-border);
            background: #FFFFFF;
            border: 1px solid var(--sa-border);
            border-radius: 8px;
            box-shadow: var(--sa-shadow-xs);
        }
        .sa-sidebar-logo {
            width: 2.15rem;
            height: 2.15rem;
            border-radius: 8px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: linear-gradient(135deg, var(--sa-primary), var(--sa-teal));
            color: #FFFFFF;
            font-weight: 900;
            letter-spacing: 0 !important;
            flex: 0 0 auto;
            box-shadow: 0 10px 20px rgba(37, 99, 235, 0.18);
        }
        .sa-sidebar-title {
            color: var(--sa-ink);
            font-size: 0.98rem;
            font-weight: 850;
            line-height: 1.1;
        }
        .sa-sidebar-subtitle {
            color: var(--sa-muted);
            font-size: 0.78rem;
            line-height: 1.25;
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
            box-shadow: var(--sa-shadow-xs);
            transition: background-color 120ms ease, border-color 120ms ease, transform 120ms ease, box-shadow 120ms ease;
        }
        [data-testid="stBaseButton-secondary"],
        .stButton > button:not([data-testid="stBaseButton-primary"]),
        .stDownloadButton > button {
            background: #FFFFFF !important;
            color: var(--sa-text) !important;
        }
        .stButton > button:hover,
        .stDownloadButton > button:hover {
            border-color: var(--sa-primary) !important;
            background: var(--sa-primary-soft) !important;
            box-shadow: var(--sa-shadow-sm);
            transform: translateY(-1px);
        }
        .main a[data-testid="stPageLink"] {
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 2.5rem;
            border: 1px solid var(--sa-border-strong);
            border-radius: 8px;
            background: #FFFFFF;
            color: var(--sa-ink) !important;
            font-weight: 750;
            text-decoration: none !important;
            box-shadow: none;
            transition: background-color 120ms ease, border-color 120ms ease, transform 120ms ease;
        }
        .main a[data-testid="stPageLink"]:hover {
            border-color: var(--sa-primary);
            background: var(--sa-surface-hover);
        }
        .main a[data-testid="stPageLink"] * {
            color: inherit !important;
            text-decoration: none !important;
        }
        [data-testid="stBaseButton-primary"] {
            background: linear-gradient(135deg, var(--sa-primary), var(--sa-primary-strong)) !important;
            border-color: var(--sa-primary) !important;
            color: #FFFFFF !important;
            box-shadow: 0 10px 22px rgba(37, 99, 235, 0.18);
        }
        [data-testid="stBaseButton-primary"] * {
            color: #FFFFFF !important;
        }
        .stButton > button:disabled,
        .stDownloadButton > button:disabled,
        [data-testid="stBaseButton-primary"]:disabled,
        [data-testid="stBaseButton-secondary"]:disabled {
            background: #EEF2F6 !important;
            border-color: var(--sa-border) !important;
            color: #98A2B3 !important;
            box-shadow: none !important;
            cursor: not-allowed !important;
            transform: none !important;
        }
        .stButton > button:disabled *,
        .stDownloadButton > button:disabled *,
        [data-testid="stBaseButton-primary"]:disabled *,
        [data-testid="stBaseButton-secondary"]:disabled * {
            color: #98A2B3 !important;
        }
        input,
        textarea,
        [data-baseweb="select"] > div,
        [data-baseweb="tag"] {
            border-radius: 8px !important;
            background-color: #FFFFFF !important;
            border-color: var(--sa-border) !important;
            color: var(--sa-text) !important;
            box-shadow: var(--sa-shadow-xs);
        }
        input:focus,
        textarea:focus,
        [data-baseweb="select"] > div:focus-within {
            border-color: var(--sa-primary) !important;
            box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.10) !important;
        }
        input::placeholder,
        textarea::placeholder {
            color: #98A2B3 !important;
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
            background: #FFFFFF !important;
            box-shadow: none;
        }
        [data-testid="stExpander"] summary {
            font-weight: 800;
            color: var(--sa-ink);
        }
        [data-testid="stMetric"],
        .stMetric {
            background:
                linear-gradient(180deg, #FFFFFF 0%, #FBFCFE 100%)
                !important;
            color: var(--sa-text) !important;
            padding: 1rem;
            border-radius: 8px;
            border: 1px solid var(--sa-border);
            box-shadow: var(--sa-shadow-xs);
        }
        [data-testid="stMetric"]:hover,
        .stMetric:hover {
            background-color: #FFFFFF !important;
        }
        [data-testid="stMetric"] *,
        .stMetric * {
            color: var(--sa-text) !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"] {
            border: 1px solid var(--sa-border) !important;
            border-radius: 8px !important;
            background: #FFFFFF !important;
            box-shadow: none !important;
            padding: 1rem !important;
        }
        [data-testid="stForm"] {
            border: 1px solid var(--sa-border) !important;
            border-radius: 8px !important;
            background: linear-gradient(180deg, #FFFFFF 0%, #FBFCFE 100%) !important;
            box-shadow: var(--sa-shadow-xs) !important;
            padding: 1.15rem !important;
        }
        div[data-testid="stDataFrame"],
        div[data-testid="stDataEditor"] {
            border: 1px solid var(--sa-border);
            border-radius: 8px;
            overflow: hidden;
            background: var(--sa-table-shell) !important;
            box-shadow: var(--sa-shadow-xs);
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
            background: transparent;
            border: 0;
            border-bottom: 1px solid var(--sa-border);
            border-radius: 0;
            padding: 0.15rem 0 1.45rem 0;
            box-shadow: none;
            margin-bottom: 1.65rem;
            overflow: hidden;
        }
        .sa-hero::before {
            content: "";
            display: block;
            width: 2.6rem;
            height: 0.22rem;
            border-radius: 999px;
            background: linear-gradient(90deg, var(--sa-primary), var(--sa-teal));
            margin-bottom: 1rem;
        }
        .sa-hero h1, .sa-hero h2, .sa-hero h3 {
            margin: 0 0 0.45rem 0 !important;
        }
        .sa-muted {
            color: var(--sa-muted);
            font-size: 0.95rem;
            line-height: 1.55;
        }
        .sa-panel {
            background: linear-gradient(180deg, #FFFFFF 0%, #FBFCFE 100%);
            border: 1px solid var(--sa-border);
            border-radius: 8px;
            padding: 1.18rem 1.22rem;
            box-shadow: var(--sa-shadow-xs);
            margin-bottom: 1.25rem;
        }
        .sa-panel:hover {
            border-color: var(--sa-border-strong);
        }
        .sa-panel-quiet {
            background: #FFFFFF;
            border: 1px solid var(--sa-border);
            border-left: 3px solid var(--sa-primary);
            border-radius: 8px;
            padding: 0.8rem 0.95rem;
        }
        .sa-toolbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
            flex-wrap: wrap;
            background: linear-gradient(180deg, #FFFFFF 0%, #FBFCFE 100%);
            border: 1px solid var(--sa-border);
            border-radius: 8px;
            padding: 0.95rem 1.05rem;
            margin: 1.15rem 0 1.45rem 0;
            box-shadow: var(--sa-shadow-xs);
        }
        .sa-section-header {
            display: flex;
            align-items: flex-end;
            justify-content: space-between;
            gap: 1rem;
            flex-wrap: wrap;
            margin: 2.1rem 0 0.85rem 0;
        }
        .sa-section-header h3 {
            margin: 0 !important;
            font-size: 1.06rem !important;
            line-height: 1.2;
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
        }
        .sa-section-header h3::before {
            content: "";
            width: 0.48rem;
            height: 0.48rem;
            border-radius: 999px;
            background: var(--sa-teal);
            box-shadow: 0 0 0 4px var(--sa-teal-soft);
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
            background: linear-gradient(135deg, #F0F6FF 0%, #F4FBFA 100%);
            border: 1px solid #C9DDFC;
            border-left: 3px solid var(--sa-primary);
            border-radius: 8px;
            padding: 1.08rem 1.15rem;
            box-shadow: var(--sa-shadow-xs);
            margin: 1rem 0 1.25rem 0;
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
            background: linear-gradient(135deg, #F0F6FF 0%, #F7FAFC 100%);
            border: 1px solid #C9DDFC;
            border-left: 3px solid var(--sa-primary);
            border-radius: 8px;
            padding: 1.1rem 1.18rem;
            box-shadow: var(--sa-shadow-xs);
            margin: 1rem 0 1.25rem 0;
        }
        .sa-home-layout {
            display: grid;
            grid-template-columns: minmax(0, 1.38fr) minmax(310px, 0.82fr);
            gap: 1.5rem;
            margin-bottom: 1.55rem;
            align-items: stretch;
        }
        .sa-home-hero {
            background: transparent;
            border: 0;
            border-bottom: 1px solid var(--sa-border);
            border-radius: 0;
            padding: 0.15rem 0 1.55rem 0;
            box-shadow: none;
            min-height: 142px;
            position: relative;
            overflow: hidden;
        }
        .sa-home-hero::before {
            content: "";
            display: block;
            width: 2.8rem;
            height: 0.22rem;
            border-radius: 999px;
            background: linear-gradient(90deg, var(--sa-primary), var(--sa-teal));
            margin-bottom: 1rem;
        }
        .sa-home-eyebrow {
            display: inline-flex;
            align-items: center;
            gap: 0.38rem;
            border: 1px solid #C7D7FE;
            background: #F4F7FF;
            color: var(--sa-primary-strong);
            border-radius: 999px;
            padding: 0.25rem 0.68rem;
            font-size: 0.76rem;
            font-weight: 850;
            margin-bottom: 0.95rem;
        }
        .sa-home-title {
            color: var(--sa-ink);
            font-size: clamp(2rem, 3.25vw, 3rem);
            line-height: 1;
            font-weight: 880;
            margin: 0 0 0.82rem 0;
        }
        .sa-home-copy {
            color: var(--sa-muted);
            max-width: 720px;
            line-height: 1.62;
            font-size: 1.02rem;
        }
        .sa-home-meta {
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
            margin-top: 1.12rem;
        }
        .sa-home-meta span {
            display: inline-flex;
            align-items: center;
            border: 1px solid var(--sa-border);
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.72);
            color: #475467;
            font-size: 0.78rem;
            font-weight: 750;
            padding: 0.28rem 0.62rem;
        }
        .sa-home-panel {
            background: linear-gradient(180deg, #FFFFFF 0%, #F8FBFF 100%);
            border: 1px solid #C7D7FE;
            border-radius: 8px;
            padding: 1.28rem 1.32rem;
            box-shadow: var(--sa-shadow-sm);
            position: relative;
            overflow: hidden;
        }
        .sa-home-panel::before {
            content: "";
            position: absolute;
            inset: 0 0 auto 0;
            height: 0.24rem;
            background: linear-gradient(90deg, var(--sa-primary), var(--sa-teal));
        }
        .sa-home-panel-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.8rem;
            margin-bottom: 0.4rem;
        }
        .sa-home-panel-icon {
            width: 2.35rem;
            height: 2.35rem;
            border-radius: 8px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: var(--sa-primary-soft);
            color: var(--sa-primary-strong);
            font-weight: 900;
            box-shadow: inset 0 0 0 1px #C7D7FE;
            flex: 0 0 auto;
        }
        .sa-home-next-title {
            color: var(--sa-ink);
            font-size: 1.16rem;
            font-weight: 850;
            line-height: 1.15;
            margin: 0.46rem 0 0.38rem;
        }
        .sa-home-next-copy {
            color: var(--sa-muted);
            font-size: 0.94rem;
            line-height: 1.5;
        }
        .sa-home-panel-foot {
            border-top: 1px solid var(--sa-border);
            color: #475467;
            font-size: 0.8rem;
            margin-top: 1.05rem;
            padding-top: 0.75rem;
        }
        .sa-custom-metrics {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
            gap: 1.1rem;
            margin: 1.35rem 0 1.85rem 0;
        }
        .sa-custom-metric {
            --metric-accent: var(--sa-primary);
            --metric-soft: var(--sa-primary-soft);
            background: linear-gradient(180deg, #FFFFFF 0%, #FBFCFE 100%);
            border: 1px solid var(--sa-border);
            border-radius: 8px;
            padding: 1.08rem 1.12rem 1.02rem;
            box-shadow: var(--sa-shadow-xs);
            position: relative;
            overflow: hidden;
        }
        .sa-custom-metric:hover {
            border-color: color-mix(in srgb, var(--metric-accent) 35%, var(--sa-border));
            background: #FFFFFF;
            transform: translateY(-1px);
            box-shadow: var(--sa-shadow-sm);
        }
        .sa-custom-metric::before {
            content: "";
            position: absolute;
            inset: 0 0 auto 0;
            height: 0.22rem;
            background: var(--metric-accent);
            opacity: 0.78;
        }
        .sa-custom-metric.sa-tone-blue {
            --metric-accent: var(--sa-primary);
            --metric-soft: var(--sa-primary-soft);
        }
        .sa-custom-metric.sa-tone-teal {
            --metric-accent: var(--sa-teal);
            --metric-soft: var(--sa-teal-soft);
        }
        .sa-custom-metric.sa-tone-amber {
            --metric-accent: var(--sa-brass);
            --metric-soft: var(--sa-brass-soft);
        }
        .sa-custom-metric.sa-tone-violet {
            --metric-accent: var(--sa-violet);
            --metric-soft: var(--sa-violet-soft);
        }
        .sa-custom-metric-top {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
            margin-bottom: 0.54rem;
        }
        .sa-custom-metric-mark {
            width: 1.82rem;
            height: 1.82rem;
            border-radius: 8px;
            background: var(--metric-soft);
            border: 1px solid color-mix(in srgb, var(--metric-accent) 28%, #FFFFFF);
            position: relative;
            flex: 0 0 auto;
        }
        .sa-custom-metric-mark::after {
            content: "";
            position: absolute;
            inset: 0.52rem;
            border-radius: 999px;
            background: var(--metric-accent);
        }
        .sa-custom-metric-label {
            color: var(--sa-muted);
            font-size: 0.78rem;
            font-weight: 800;
            text-transform: uppercase;
        }
        .sa-custom-metric-value {
            color: var(--sa-ink);
            font-size: 1.82rem;
            font-weight: 840;
            line-height: 1;
            margin-top: 0.12rem;
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
            background: linear-gradient(180deg, #FFFFFF 0%, #FBFCFE 100%);
            border: 1px solid var(--sa-border);
            border-radius: 8px;
            padding: 1rem;
            min-height: 142px;
            box-shadow: var(--sa-shadow-xs);
            display: grid;
            gap: 0.55rem;
        }
        .sa-nav-card:hover {
            border-color: var(--sa-primary);
            background: #FFFFFF;
            box-shadow: var(--sa-shadow-sm);
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
            gap: 0.9rem;
            margin: 1rem 0;
        }
        .sa-stat-card {
            background: linear-gradient(180deg, #FFFFFF 0%, #FBFCFE 100%);
            border: 1px solid var(--sa-border);
            border-radius: 8px;
            padding: 1rem 1.08rem;
            box-shadow: var(--sa-shadow-xs);
        }
        .sa-stat-card:hover {
            background: #FFFFFF;
            border-color: var(--sa-border-strong);
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
            background: rgba(255, 255, 255, 0.78);
            border: 1px solid var(--sa-border);
            border-radius: 8px;
            padding: 0.72rem 0.78rem;
            min-height: 86px;
            box-shadow: var(--sa-shadow-xs);
            transition: border-color 120ms ease, color 120ms ease, box-shadow 120ms ease, transform 120ms ease;
        }
        .sa-step:hover {
            border-color: var(--sa-primary);
            box-shadow: var(--sa-shadow-sm);
            transform: translateY(-1px);
        }
        .sa-step-active {
            border-color: var(--sa-primary);
            background: linear-gradient(180deg, #FFFFFF 0%, #F3F7FF 100%);
            box-shadow: 0 10px 24px rgba(37, 99, 235, 0.10);
        }
        .sa-step-done {
            border-color: #C9D8E8;
            background: #FFFFFF;
        }
        .sa-step-num {
            width: 2rem;
            height: 2rem;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-radius: 999px;
            background: var(--sa-primary-soft);
            color: var(--sa-primary-strong);
            font-weight: 800;
            flex-shrink: 0;
        }
        .sa-step-active .sa-step-num {
            background: var(--sa-primary);
            color: #FFFFFF;
        }
        .sa-step-done .sa-step-num {
            background: var(--sa-teal-soft);
            color: var(--sa-teal);
        }
        .sa-step-title {
            font-weight: 820;
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
            padding: 0.22rem 0.62rem;
            font-size: 0.78rem;
            font-weight: 750;
            color: var(--sa-muted);
            background: var(--sa-surface-2);
            white-space: nowrap;
            box-shadow: var(--sa-shadow-xs);
        }
        .sa-pill-good { color: #067647; background: #ECFDF3; border-color: #ABEFC6; }
        .sa-pill-warn { color: #B54708; background: #FFFAEB; border-color: #FEDF89; }
        .sa-pill-bad { color: #B42318; background: #FEF3F2; border-color: #FECDCA; }
        .sa-pill-blue { color: var(--sa-primary-strong); background: var(--sa-primary-soft); border-color: #B2CCFF; }
        .sa-pill-neutral { color: #475467; background: #F2F4F7; border-color: #D0D5DD; }
        .sa-pill-purple { color: #6941C6; background: #F4F3FF; border-color: #D9D6FE; }
        .sa-pill-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.4rem;
            align-items: center;
            margin: 0.55rem 0 0.1rem 0;
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
            border: 1px solid #C9DDFC;
            border-left: 3px solid var(--sa-primary);
            background: linear-gradient(135deg, #F0F6FF 0%, #F8FBFF 100%);
            color: var(--sa-primary-strong);
            border-radius: 8px;
            padding: 0.92rem 1.05rem;
            margin: 1rem 0;
            box-shadow: var(--sa-shadow-xs);
        }
        .sa-danger {
            border-color: #F04438;
            background: #FEF3F2;
            color: #B42318;
        }
        .sa-warning {
            border-color: #F79009;
            background: #FFFAEB;
            color: #B54708;
        }
        .sa-success {
            border-color: #12B76A;
            background: #ECFDF3;
            color: #067647;
        }
        .sa-command-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
            gap: 0.85rem;
            margin: 0.85rem 0;
        }
        .sa-action-card {
            background: linear-gradient(180deg, #FFFFFF 0%, #FBFCFE 100%);
            border: 1px solid var(--sa-border);
            border-radius: 8px;
            padding: 1.05rem;
            min-height: 138px;
            box-shadow: var(--sa-shadow-xs);
        }
        .sa-action-card:hover {
            border-color: var(--sa-primary);
            box-shadow: var(--sa-shadow-sm);
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
        @media (max-width: 1120px) {
            [data-testid="stMainBlockContainer"],
            .stMainBlockContainer,
            .main .block-container {
                padding-left: 1.35rem !important;
                padding-right: 1.35rem !important;
            }
        }
        @media (max-width: 980px) {
            .sa-home-layout {
                grid-template-columns: 1fr;
                gap: 1.05rem;
            }
            .sa-home-hero {
                min-height: 0;
            }
            .sa-custom-metrics {
                grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            }
        }
        @media (max-width: 760px) {
            [data-testid="stMainBlockContainer"],
            .stMainBlockContainer,
            .main .block-container {
                padding-left: 0.9rem !important;
                padding-right: 0.9rem !important;
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
