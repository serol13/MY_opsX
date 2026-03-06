import streamlit as st
import pandas as pd
import json
import base64
import io
import requests
from datetime import datetime, date
import uuid
import plotly.express as px
import plotly.graph_objects as go
from collections import Counter
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="QA Viz Tracker",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── GitHub config ─────────────────────────────────────────────────────────────
GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
GITHUB_REPO  = st.secrets["GITHUB_REPO"]
FILE_PATH    = "tickets.json"
BRANCH       = "main"
GITHUB_API   = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{FILE_PATH}"
HEADERS      = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

# ── GitHub helpers ────────────────────────────────────────────────────────────
def gh_load():
    r = requests.get(GITHUB_API, headers=HEADERS)
    if r.status_code == 404:
        return [], None
    r.raise_for_status()
    data    = r.json()
    content = base64.b64decode(data["content"]).decode("utf-8")
    return json.loads(content), data["sha"]

def gh_save(tickets, sha):
    content = base64.b64encode(
        json.dumps(tickets, indent=2, default=str).encode("utf-8")
    ).decode("utf-8")
    payload = {
        "message": f"Update tickets [{datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC]",
        "content": content,
        "branch":  BRANCH,
    }
    if sha:
        payload["sha"] = sha
    r = requests.put(GITHUB_API, headers=HEADERS, json=payload)
    r.raise_for_status()
    return r.json()["content"]["sha"]

# ── Session bootstrap ─────────────────────────────────────────────────────────
if "tickets" not in st.session_state:
    with st.spinner("Loading tickets from GitHub..."):
        try:
            st.session_state.tickets, st.session_state.gh_sha = gh_load()
        except Exception as e:
            st.error(f"Could not reach GitHub: {e}")
            st.session_state.tickets, st.session_state.gh_sha = [], None

def save_and_sync(tickets):
    try:
        new_sha = gh_save(tickets, st.session_state.get("gh_sha"))
        st.session_state.gh_sha  = new_sha
        st.session_state.tickets = tickets
    except Exception as e:
        st.error(f"GitHub sync failed: {e}")

# ── DHL Colour Palette ────────────────────────────────────────────────────────
# Primary: DHL Yellow #FFCC00, DHL Red #D40511
# Neutrals: white bg, dark charcoal text
DHL_YELLOW  = "#FFCC00"
DHL_RED     = "#D40511"
DHL_DARK    = "#1A1A1A"
DHL_GRAY    = "#6B6B6B"
DHL_LIGHT   = "#F5F5F5"
DHL_BORDER  = "#E0E0E0"
DHL_WHITE   = "#FFFFFF"

PLATFORM_COLORS = {"Splunk": DHL_RED, "Power BI": "#0078D4", "Others": "#6B6B6B"}
STATUS_COLORS   = {
    "Backlog":     "#9E9E9E",
    "In Progress": "#0078D4",
    "In Review":   "#FF8C00",
    "Done":        "#2E7D32",
    "Blocked":     DHL_RED,
}
PRIORITY_COLORS = {
    "Low":      "#2E7D32",
    "Medium":   "#FF8C00",
    "High":     DHL_RED,
    "Critical": "#6A0DAD",
}
PRIORITY_ORDER = ["Low", "Medium", "High", "Critical"]
STATUS_ORDER   = ["Backlog", "In Progress", "In Review", "Blocked", "Done"]

def badge(label, bg_color, text_color="#FFFFFF"):
    return (
        f'<span style="background:{bg_color};color:{text_color};padding:3px 12px;'
        f'border-radius:4px;font-size:12px;font-weight:700;letter-spacing:.3px">{label}</span>'
    )

def progress_bar_html(pct, color=DHL_YELLOW):
    text_color = DHL_DARK if color == DHL_YELLOW else "#FFFFFF"
    return (
        f'<div style="background:{DHL_BORDER};border-radius:4px;height:12px;width:100%;overflow:hidden;margin:6px 0 2px">'
        f'<div style="background:{color};width:{pct}%;height:100%;border-radius:4px"></div></div>'
        f'<small style="color:{DHL_GRAY};font-size:12px">{pct}% complete</small>'
    )

# ── Excel export builder ──────────────────────────────────────────────────────
def _thin_border():
    s = Side(style="thin", color="E0E0E0")
    return Border(left=s, right=s, top=s, bottom=s)

def _hdr(ws, row, col, value, bg, fg="FFFFFF", merge_to=None, height=None):
    cell = ws.cell(row=row, column=col, value=value)
    cell.fill = PatternFill("solid", start_color=bg)
    cell.font = Font(bold=True, color=fg, name="Arial", size=10)
    cell.alignment = Alignment(horizontal="center", vertical="center")
    cell.border = _thin_border()
    if merge_to:
        ws.merge_cells(f"{get_column_letter(col)}{row}:{get_column_letter(merge_to)}{row}")
    if height:
        ws.row_dimensions[row].height = height
    return cell

def build_excel_export(tickets):
    # strip leading # from hex colours for openpyxl
    def h(c): return c.lstrip("#")

    P_COLORS = {k: h(v) for k, v in PLATFORM_COLORS.items()}
    S_COLORS = {k: h(v) for k, v in STATUS_COLORS.items()}
    R_COLORS = {k: h(v) for k, v in PRIORITY_COLORS.items()}

    wb = Workbook()

    # ── Sheet 1: All Tickets ──────────────────────────────────────────────
    ws = wb.active
    ws.title = "All Tickets"
    ws.sheet_view.showGridLines = False

    _hdr(ws, 1, 1, "QA VISUALIZATION TRACKER — TICKET EXPORT",
         h(DHL_YELLOW), h(DHL_DARK), merge_to=11, height=36)
    ws["A1"].font = Font(bold=True, color=h(DHL_DARK), name="Arial", size=14)

    _hdr(ws, 2, 1,
         f"Generated: {datetime.now().strftime('%d %B %Y, %H:%M')}  |  Total: {len(tickets)} tickets",
         h(DHL_DARK), h(DHL_YELLOW), merge_to=11, height=20)
    ws["A2"].font = Font(italic=True, color=h(DHL_YELLOW), name="Arial", size=10)

    ws.row_dimensions[3].height = 5

    col_headers = ["Ticket ID","Title","Platform","Priority","Status","Progress %",
                   "Requestor","Due Date","Tags","Description","Created"]
    col_widths  = [14, 36, 12, 12, 14, 13, 16, 14, 22, 50, 20]
    for i, (hd, w) in enumerate(zip(col_headers, col_widths), 1):
        _hdr(ws, 4, i, hd, h(DHL_RED), "FFFFFF")
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[4].height = 22

    for r, t in enumerate(tickets, 5):
        row_bg = "FFFFFF" if r % 2 == 1 else "F5F5F5"
        data = [
            t.get("id",""), t.get("title",""), t.get("platform",""),
            t.get("priority",""), t.get("status",""), t.get("progress", 0),
            t.get("requestor",""), t.get("due_date",""),
            ", ".join(t.get("tags",[])), t.get("description",""),
            t.get("created_at","")[:10],
        ]
        ws.row_dimensions[r].height = 20
        for ci, val in enumerate(data, 1):
            cell = ws.cell(row=r, column=ci, value=val)
            cell.border = _thin_border()
            cell.font = Font(name="Arial", size=10, color=h(DHL_DARK))
            cell.alignment = Alignment(vertical="center", wrap_text=(ci == 10))

            if ci == 3:    # Platform
                cell.fill = PatternFill("solid", start_color=P_COLORS.get(val, h(DHL_GRAY)))
                cell.font = Font(name="Arial", size=10, color="FFFFFF", bold=True)
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif ci == 4:  # Priority
                cell.fill = PatternFill("solid", start_color=R_COLORS.get(val, h(DHL_GRAY)))
                cell.font = Font(name="Arial", size=10, color="FFFFFF", bold=True)
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif ci == 5:  # Status
                cell.fill = PatternFill("solid", start_color=S_COLORS.get(val, h(DHL_GRAY)))
                cell.font = Font(name="Arial", size=10, color="FFFFFF", bold=True)
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif ci == 6:  # Progress
                cell.fill = PatternFill("solid", start_color=row_bg)
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.number_format = '0"%"'
            else:
                cell.fill = PatternFill("solid", start_color=row_bg)

    ws.freeze_panes = "A5"

    # ── Sheet 2: Summary ──────────────────────────────────────────────────
    ws2 = wb.create_sheet("Summary")
    ws2.sheet_view.showGridLines = False
    for col, w in zip("ABCD", [22, 12, 14, 14]):
        ws2.column_dimensions[col].width = w

    _hdr(ws2, 1, 1, "TICKET SUMMARY", h(DHL_YELLOW), h(DHL_DARK), merge_to=4, height=32)
    ws2["A1"].font = Font(bold=True, color=h(DHL_DARK), name="Arial", size=13)
    _hdr(ws2, 2, 1, f"As of {datetime.now().strftime('%d %B %Y')}",
         h(DHL_DARK), h(DHL_YELLOW), merge_to=4, height=18)

    status_counts   = Counter(t["status"]   for t in tickets)
    priority_counts = Counter(t["priority"] for t in tickets)
    platform_counts = Counter(t["platform"] for t in tickets)

    def summary_section(ws, start_row, label, items, color_map, order):
        # Section label row - spans all columns
        _hdr(ws, start_row, 1, label, h(DHL_RED), "FFFFFF", merge_to=4, height=20)
        # Column sub-headers on the NEXT row (avoids writing into merged cells)
        for ci, col_label in enumerate(["Category", "Count", "% of Total"], 1):
            _hdr(ws, start_row + 1, ci, col_label, h(DHL_DARK), "FFFFFF")
        ws.row_dimensions[start_row + 1].height = 18
        r = start_row + 2
        total = sum(items.values())
        for key in order:
            cnt = items.get(key, 0)
            ca = ws.cell(row=r, column=1, value=key)
            ca.fill = PatternFill("solid", start_color=color_map.get(h(key) if key in color_map else key, h(DHL_GRAY)))

            # Use correct colour map (already stripped)
            bg = color_map.get(key, h(DHL_GRAY))
            ca.fill = PatternFill("solid", start_color=bg)
            ca.font = Font(bold=True, color="FFFFFF", name="Arial", size=10)
            ca.alignment = Alignment(horizontal="center", vertical="center")
            ca.border = _thin_border()

            cb = ws.cell(row=r, column=2, value=cnt)
            cb.font = Font(name="Arial", size=10, bold=True, color=h(DHL_DARK))
            cb.alignment = Alignment(horizontal="center")
            cb.border = _thin_border()
            cb.fill = PatternFill("solid", start_color="FFFFFF")

            pct = round(cnt / total * 100, 1) if total else 0
            cc = ws.cell(row=r, column=3, value=pct)
            cc.number_format = '0.0"%"'
            cc.font = Font(name="Arial", size=10, color=h(DHL_DARK))
            cc.alignment = Alignment(horizontal="center")
            cc.border = _thin_border()
            cc.fill = PatternFill("solid", start_color="F5F5F5")
            ws.row_dimensions[r].height = 20
            r += 1

        # Total row
        ct = ws.cell(row=r, column=1, value="TOTAL")
        ct.fill = PatternFill("solid", start_color=h(DHL_DARK))
        ct.font = Font(bold=True, color="FFFFFF", name="Arial")
        ct.alignment = Alignment(horizontal="center")
        ct.border = _thin_border()
        ctv = ws.cell(row=r, column=2, value=total)
        ctv.fill = PatternFill("solid", start_color=h(DHL_YELLOW))
        ctv.font = Font(bold=True, name="Arial", color=h(DHL_DARK))
        ctv.alignment = Alignment(horizontal="center")
        ctv.border = _thin_border()
        ws.row_dimensions[r].height = 22
        return r + 2

    next_row = summary_section(ws2, 4, "BY STATUS",   status_counts,
                               {k: h(v) for k,v in STATUS_COLORS.items()}, STATUS_ORDER)
    next_row = summary_section(ws2, next_row, "BY PRIORITY", priority_counts,
                               {k: h(v) for k,v in PRIORITY_COLORS.items()}, PRIORITY_ORDER)
    summary_section(ws2, next_row, "BY PLATFORM", platform_counts,
                    {k: h(v) for k,v in PLATFORM_COLORS.items()}, ["Splunk","Power BI","Others"])

    # ── Sheet 3: Comments ─────────────────────────────────────────────────
    ws3 = wb.create_sheet("Comments")
    ws3.sheet_view.showGridLines = False
    _hdr(ws3, 1, 1, "COMMENT HISTORY", h(DHL_YELLOW), h(DHL_DARK), merge_to=4, height=30)
    ws3["A1"].font = Font(bold=True, color=h(DHL_DARK), name="Arial", size=13)

    for i, (hd, w) in enumerate(zip(["Ticket ID","Ticket Title","Timestamp","Comment"],
                                     [14, 36, 20, 72]), 1):
        _hdr(ws3, 3, i, hd, h(DHL_RED), "FFFFFF")
        ws3.column_dimensions[get_column_letter(i)].width = w
    ws3.row_dimensions[3].height = 22
    ws3.freeze_panes = "A4"

    cmt_row = 4
    for t in tickets:
        for cmt in t.get("comments", []):
            bg = "FFFFFF" if cmt_row % 2 == 0 else "F5F5F5"
            for ci, val in enumerate([
                t["id"], t["title"],
                cmt["timestamp"][:16].replace("T", " "),
                cmt["text"]
            ], 1):
                cell = ws3.cell(row=cmt_row, column=ci, value=val)
                cell.fill = PatternFill("solid", start_color=bg)
                cell.font = Font(name="Arial", size=10, color=h(DHL_DARK))
                cell.border = _thin_border()
                cell.alignment = Alignment(vertical="center", wrap_text=(ci == 4))
            ws3.row_dimensions[cmt_row].height = 20
            cmt_row += 1

    if cmt_row == 4:
        c = ws3.cell(row=4, column=1, value="No comments recorded yet.")
        c.font = Font(italic=True, color=h(DHL_GRAY), name="Arial")

    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return out.getvalue()

# ── Streamlit theme override via config ───────────────────────────────────────
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Delivery+Grotesque:wght@400;700&family=Roboto:wght@400;500;700&display=swap');

/* Global reset to light theme */
html, body, [class*="css"], .stApp {{
    font-family: 'Roboto', sans-serif !important;
    background-color: {DHL_LIGHT} !important;
    color: {DHL_DARK} !important;
}}

/* Main content area */
.main .block-container {{
    background-color: {DHL_LIGHT};
    padding-top: 1.5rem !important;
    max-width: 1400px;
}}

/* Sidebar */
[data-testid="stSidebar"] {{
    background-color: {DHL_DARK} !important;
    border-right: 4px solid {DHL_YELLOW} !important;
}}
[data-testid="stSidebar"] * {{
    color: {DHL_WHITE} !important;
}}
[data-testid="stSidebar"] .stRadio label {{
    color: {DHL_WHITE} !important;
    font-weight: 500;
}}
[data-testid="stSidebar"] hr {{
    border-color: #444 !important;
}}

/* Top header bar */
.dhl-header {{
    background: {DHL_YELLOW};
    padding: 14px 24px;
    border-radius: 8px;
    margin-bottom: 24px;
    display: flex;
    align-items: center;
    gap: 16px;
    border-left: 6px solid {DHL_RED};
}}
.dhl-header h1 {{
    margin: 0;
    font-size: 22px;
    font-weight: 700;
    color: {DHL_DARK};
    letter-spacing: .5px;
    text-transform: uppercase;
}}
.dhl-header span {{
    font-size: 13px;
    color: #555;
    font-weight: 500;
}}

/* Metric card */
.metric-card {{
    background: {DHL_WHITE};
    border: 1px solid {DHL_BORDER};
    border-top: 4px solid {DHL_YELLOW};
    border-radius: 8px;
    padding: 18px 20px;
    margin-bottom: 8px;
    box-shadow: 0 1px 4px rgba(0,0,0,.06);
}}
.metric-card .val {{
    font-size: 2.2rem;
    font-weight: 700;
    color: {DHL_DARK};
    line-height: 1;
    margin-bottom: 4px;
}}
.metric-card .lbl {{
    font-size: 12px;
    font-weight: 600;
    color: {DHL_GRAY};
    text-transform: uppercase;
    letter-spacing: .06em;
}}
.metric-card.red {{ border-top-color: {DHL_RED}; }}
.metric-card.green {{ border-top-color: #2E7D32; }}
.metric-card.blue {{ border-top-color: #0078D4; }}
.metric-card.orange {{ border-top-color: #FF8C00; }}

/* Section header */
.section-header {{
    font-size: 18px;
    font-weight: 700;
    color: {DHL_DARK};
    border-left: 5px solid {DHL_YELLOW};
    padding-left: 12px;
    margin: 28px 0 16px;
    text-transform: uppercase;
    letter-spacing: .04em;
}}

/* Ticket card */
.ticket-card {{
    background: {DHL_WHITE};
    border: 1px solid {DHL_BORDER};
    border-left: 5px solid {DHL_YELLOW};
    border-radius: 8px;
    padding: 16px 20px;
    margin-bottom: 12px;
    box-shadow: 0 1px 3px rgba(0,0,0,.05);
}}
.ticket-card:hover {{
    border-left-color: {DHL_RED};
    box-shadow: 0 3px 10px rgba(0,0,0,.08);
}}
.ticket-id {{
    font-size: 11px;
    font-weight: 700;
    color: {DHL_GRAY};
    text-transform: uppercase;
    letter-spacing: .08em;
    margin-bottom: 4px;
}}
.ticket-title {{
    font-size: 16px;
    font-weight: 700;
    color: {DHL_DARK};
    margin: 4px 0 10px;
}}
.pills {{
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    margin: 8px 0 10px;
}}

/* Sync badge */
.sync-badge {{
    background: #333;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 5px 12px;
    font-size: 12px;
    color: {DHL_YELLOW};
    font-weight: 600;
    display: inline-block;
    margin-bottom: 10px;
    letter-spacing: .04em;
}}

/* Buttons */
.stButton > button {{
    background-color: {DHL_YELLOW} !important;
    color: {DHL_DARK} !important;
    border: none !important;
    border-radius: 5px !important;
    font-weight: 700 !important;
    font-size: 14px !important;
    padding: 10px 24px !important;
    letter-spacing: .02em;
    transition: background .2s;
}}
.stButton > button:hover {{
    background-color: {DHL_RED} !important;
    color: {DHL_WHITE} !important;
}}

/* Form inputs — force light */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea {{
    background: {DHL_WHITE} !important;
    color: {DHL_DARK} !important;
    border: 1px solid {DHL_BORDER} !important;
    border-radius: 5px !important;
    font-size: 14px !important;
}}
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {{
    border-color: {DHL_YELLOW} !important;
    box-shadow: 0 0 0 2px {DHL_YELLOW}44 !important;
}}
.stSelectbox > div > div,
.stMultiSelect > div > div {{
    background: {DHL_WHITE} !important;
    color: {DHL_DARK} !important;
    border-color: {DHL_BORDER} !important;
}}

/* Slider */
.stSlider > div > div > div > div {{
    background: {DHL_YELLOW} !important;
}}

/* Tabs */
.stTabs [data-baseweb="tab"] {{
    font-weight: 600;
    color: {DHL_GRAY};
}}
.stTabs [aria-selected="true"] {{
    color: {DHL_RED} !important;
    border-bottom-color: {DHL_RED} !important;
}}

/* Dataframe */
[data-testid="stDataFrame"] {{
    border: 1px solid {DHL_BORDER} !important;
    border-radius: 8px !important;
}}

/* Radio */
.stRadio > div {{
    gap: 8px;
}}

/* Hide Streamlit chrome */
#MainMenu, footer, header {{ visibility: hidden; }}

/* Alert boxes */
.stSuccess {{ background: #E8F5E9 !important; color: #1B5E20 !important; border-left-color: #2E7D32 !important; }}
.stError   {{ background: #FFEBEE !important; color: #B71C1C !important; border-left-color: {DHL_RED} !important; }}
.stInfo    {{ background: #FFF9E6 !important; color: #5C4A00 !important; border-left-color: {DHL_YELLOW} !important; }}
</style>
""", unsafe_allow_html=True)

tickets = st.session_state.tickets

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="padding:16px 0 8px">
      <div style="font-size:24px;font-weight:900;color:#FFCC00;letter-spacing:1px">DHL</div>
      <div style="font-size:13px;color:#aaa;margin-top:2px">QA Visualization Tracker</div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown('<div class="sync-badge">Synced to GitHub</div>', unsafe_allow_html=True)
    st.markdown("---")
    page = st.radio("Navigation", [
        "Dashboard", "Submit Request", "All Tickets", "Update Ticket"
    ], label_visibility="collapsed")
    st.markdown("---")
    total   = len(tickets)
    done    = sum(1 for t in tickets if t["status"] == "Done")
    blocked = sum(1 for t in tickets if t["status"] == "Blocked")
    st.markdown(f"""
    <div style="font-size:13px;color:#ccc;line-height:2">
      <b style="color:#fff">Total:</b> {total}<br>
      <b style="color:#FFCC00">Done:</b> {done}<br>
      <b style="color:#D40511">Blocked:</b> {blocked}
    </div>
    """, unsafe_allow_html=True)
    st.markdown("")
    st.markdown("")
    if tickets:
        excel_bytes = build_excel_export(tickets)
        st.download_button(
            label="Export to Excel",
            data=excel_bytes,
            file_name=f"QA_Tickets_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    st.markdown("---")
    if st.button("Refresh from GitHub"):
        with st.spinner("Syncing..."):
            try:
                st.session_state.tickets, st.session_state.gh_sha = gh_load()
                st.rerun()
            except Exception as e:
                st.error(str(e))

# ── Page header ───────────────────────────────────────────────────────────────
PAGE_TITLES = {
    "Dashboard":      ("Dashboard Overview", "Track all QA visualization requests at a glance"),
    "Submit Request": ("Submit New Request", "Log a new Splunk, Power BI, or other visualization request"),
    "All Tickets":    ("All Tickets", "Browse, filter, and search all submitted tickets"),
    "Update Ticket":  ("Update Ticket", "Update status, progress, and add comments"),
}
title, subtitle = PAGE_TITLES.get(page, ("QA Viz Tracker", ""))
st.markdown(f"""
<div class="dhl-header">
  <div>
    <h1>{title}</h1>
    <span>{subtitle}</span>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Plotly chart defaults ─────────────────────────────────────────────────────
CHART_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="#FFFFFF",
    font=dict(color=DHL_DARK, family="Roboto"),
    title_font=dict(color=DHL_DARK, size=15, family="Roboto"),
    margin=dict(t=40, b=20, l=10, r=10),
)

# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
if page == "Dashboard":
    df = pd.DataFrame(tickets) if tickets else pd.DataFrame(
        columns=["id","title","platform","priority","status","progress",
                 "created_at","due_date","description","requestor","tags"])

    # KPI cards
    c1,c2,c3,c4,c5 = st.columns(5)
    kpis = [
        (c1, "Total Tickets",  len(df),                                              "", ""),
        (c2, "In Progress",    len(df[df.status=="In Progress"]) if len(df) else 0,  "blue", ""),
        (c3, "In Review",      len(df[df.status=="In Review"])   if len(df) else 0,  "orange", ""),
        (c4, "Blocked",        len(df[df.status=="Blocked"])     if len(df) else 0,  "red", ""),
        (c5, "Done",           len(df[df.status=="Done"])        if len(df) else 0,  "green", ""),
    ]
    for col, label, value, cls, _ in kpis:
        with col:
            st.markdown(f"""
            <div class="metric-card {cls}">
              <div class="val">{value}</div>
              <div class="lbl">{label}</div>
            </div>""", unsafe_allow_html=True)

    if not df.empty:
        st.markdown("---")
        r1a, r1b = st.columns(2)

        with r1a:
            sc = df["status"].value_counts().reset_index()
            sc.columns = ["Status", "Count"]
            fig = px.pie(sc, names="Status", values="Count", hole=0.55,
                         title="Tickets by Status", color="Status",
                         color_discrete_map=STATUS_COLORS)
            fig.update_layout(**CHART_LAYOUT)
            fig.update_traces(textfont_color=DHL_WHITE)
            st.plotly_chart(fig, use_container_width=True)

        with r1b:
            pc = df["platform"].value_counts().reset_index()
            pc.columns = ["Platform", "Count"]
            fig2 = px.bar(pc, x="Platform", y="Count", title="Tickets by Platform",
                          color="Platform", color_discrete_map=PLATFORM_COLORS, text="Count")
            fig2.update_layout(**CHART_LAYOUT,
                xaxis=dict(gridcolor=DHL_BORDER, linecolor=DHL_BORDER),
                yaxis=dict(gridcolor=DHL_BORDER, linecolor=DHL_BORDER))
            fig2.update_traces(textposition="outside", marker_line_width=0,
                               textfont_color=DHL_DARK)
            st.plotly_chart(fig2, use_container_width=True)

        r2a, r2b = st.columns(2)

        with r2a:
            pric = df["priority"].value_counts().reindex(PRIORITY_ORDER, fill_value=0).reset_index()
            pric.columns = ["Priority", "Count"]
            fig3 = px.bar(pric, x="Priority", y="Count", title="Tickets by Priority",
                          color="Priority", color_discrete_map=PRIORITY_COLORS, text="Count")
            fig3.update_layout(**CHART_LAYOUT,
                xaxis=dict(gridcolor=DHL_BORDER), yaxis=dict(gridcolor=DHL_BORDER))
            fig3.update_traces(textposition="outside", marker_line_width=0,
                               textfont_color=DHL_DARK)
            st.plotly_chart(fig3, use_container_width=True)

        with r2b:
            ap = df.groupby("status")["progress"].mean().reset_index()
            ap.columns = ["Status", "Avg Progress"]
            fig4 = px.bar(ap, x="Status", y="Avg Progress", title="Avg Progress % by Status",
                          color="Status", color_discrete_map=STATUS_COLORS,
                          text=ap["Avg Progress"].round(1).astype(str) + "%")
            fig4.update_layout(**CHART_LAYOUT,
                xaxis=dict(gridcolor=DHL_BORDER), yaxis=dict(gridcolor=DHL_BORDER, range=[0,115]))
            fig4.update_traces(textposition="outside", marker_line_width=0,
                               textfont_color=DHL_DARK)
            st.plotly_chart(fig4, use_container_width=True)

        st.markdown('<div class="section-header">Recent Tickets</div>', unsafe_allow_html=True)
        for t in sorted(tickets, key=lambda x: x.get("created_at", ""), reverse=True)[:5]:
            bar_color = STATUS_COLORS.get(t["status"], DHL_YELLOW)
            st.markdown(f"""
            <div class="ticket-card">
              <div class="ticket-id">{t['id']}</div>
              <div class="ticket-title">{t['title']}</div>
              <div class="pills">
                {badge(t['platform'], PLATFORM_COLORS.get(t['platform'], DHL_GRAY))}
                {badge(t['status'],   STATUS_COLORS.get(t['status'],   DHL_GRAY))}
                {badge(t['priority'], PRIORITY_COLORS.get(t['priority'], DHL_GRAY))}
              </div>
              {progress_bar_html(t.get('progress', 0), bar_color)}
            </div>""", unsafe_allow_html=True)
    else:
        st.info("No tickets yet. Head to Submit Request to log your first one.")

# ══════════════════════════════════════════════════════════════════════════════
# SUBMIT REQUEST
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Submit Request":
    with st.form("submit_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            title     = st.text_input("Ticket Title *", placeholder="e.g. Sales Dashboard KPI refresh")
            platform  = st.selectbox("Platform *", ["Splunk", "Power BI", "Others"])
            priority  = st.selectbox("Priority *", PRIORITY_ORDER)
        with c2:
            requestor = st.text_input("Requestor Name *", placeholder="Your name")
            due_date  = st.date_input("Target Due Date", value=date.today())
            tags      = st.text_input("Tags (comma-separated)", placeholder="e.g. kpi, finance, Q2")
        description = st.text_area("Description / Requirements *",
            placeholder="Describe the dashboard or report request in detail...", height=160)
        submitted = st.form_submit_button("Submit Ticket")

    if submitted:
        if not title or not requestor or not description:
            st.error("Please fill in all required fields (*).")
        else:
            ticket_id = "QA-" + str(uuid.uuid4())[:6].upper()
            new_ticket = {
                "id":          ticket_id,
                "title":       title,
                "platform":    platform,
                "priority":    priority,
                "status":      "Backlog",
                "progress":    0,
                "requestor":   requestor,
                "due_date":    str(due_date),
                "tags":        [t.strip() for t in tags.split(",") if t.strip()],
                "description": description,
                "created_at":  datetime.now().isoformat(),
                "updated_at":  datetime.now().isoformat(),
                "comments":    [],
            }
            with st.spinner("Saving to GitHub..."):
                save_and_sync(st.session_state.tickets + [new_ticket])
            st.success(f"Ticket {ticket_id} submitted and saved to GitHub.")
            st.markdown(f"""
            <div class="ticket-card">
              <div class="ticket-id">{ticket_id}</div>
              <div class="ticket-title">{title}</div>
              <div class="pills">
                {badge(platform, PLATFORM_COLORS.get(platform, DHL_GRAY))}
                {badge('Backlog', STATUS_COLORS['Backlog'])}
                {badge(priority,  PRIORITY_COLORS.get(priority, DHL_GRAY))}
              </div>
            </div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# ALL TICKETS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "All Tickets":
    if not tickets:
        st.info("No tickets yet. Submit your first request!")
    else:
        # Export button at top
        excel_bytes = build_excel_export(tickets)
        st.download_button(
            label="Export All Tickets to Excel",
            data=excel_bytes,
            file_name=f"QA_Tickets_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        st.markdown("")
        fc1, fc2, fc3, fc4 = st.columns(4)
        with fc1: f_platform = st.multiselect("Platform", ["Splunk","Power BI","Others"], default=["Splunk","Power BI","Others"])
        with fc2: f_status   = st.multiselect("Status", STATUS_ORDER, default=STATUS_ORDER)
        with fc3: f_priority = st.multiselect("Priority", PRIORITY_ORDER, default=PRIORITY_ORDER)
        with fc4: f_search   = st.text_input("Search", placeholder="title or requestor...")

        filtered = [
            t for t in tickets
            if t["platform"] in f_platform
            and t["status"] in f_status
            and t["priority"] in f_priority
            and (not f_search
                 or f_search.lower() in t["title"].lower()
                 or f_search.lower() in t.get("requestor", "").lower())
        ]

        sc1, sc2 = st.columns([2, 1])
        with sc1:
            sort_by = st.selectbox("Sort by", [
                "Created (newest)", "Created (oldest)",
                "Priority (high to low)", "Progress (high to low)", "Due Date"
            ])
        with sc2:
            view_mode = st.radio("View", ["Cards", "Table"], horizontal=True)

        def sort_key(t):
            if sort_by == "Created (newest)":       return t.get("created_at", "")
            if sort_by == "Created (oldest)":       return t.get("created_at", "")
            if sort_by == "Priority (high to low)": return PRIORITY_ORDER.index(t["priority"])
            if sort_by == "Progress (high to low)": return -t.get("progress", 0)
            return t.get("due_date", "")

        reverse = sort_by in ["Created (newest)", "Progress (high to low)"]
        filtered = sorted(filtered, key=sort_key, reverse=reverse)
        st.caption(f"Showing {len(filtered)} of {len(tickets)} tickets")

        if view_mode == "Cards":
            for t in filtered:
                bar_color = STATUS_COLORS.get(t["status"], DHL_YELLOW)
                tag_html = " ".join(
                    f'<span style="background:{DHL_LIGHT};color:{DHL_DARK};border:1px solid {DHL_BORDER};'
                    f'padding:1px 8px;border-radius:4px;font-size:11px;font-weight:600">{tag}</span>'
                    for tag in t.get("tags", [])
                )
                st.markdown(f"""
                <div class="ticket-card">
                  <div class="ticket-id">{t['id']} · {t.get('requestor','')} · Due {t.get('due_date','—')}</div>
                  <div class="ticket-title">{t['title']}</div>
                  <div class="pills">
                    {badge(t['platform'], PLATFORM_COLORS.get(t['platform'], DHL_GRAY))}
                    {badge(t['status'],   STATUS_COLORS.get(t['status'],     DHL_GRAY))}
                    {badge(t['priority'], PRIORITY_COLORS.get(t['priority'], DHL_GRAY))}
                    {tag_html}
                  </div>
                  {progress_bar_html(t.get('progress', 0), bar_color)}
                  <p style="color:{DHL_GRAY};font-size:13px;margin-top:8px">
                    {t.get('description','')[:200]}{'...' if len(t.get('description',''))>200 else ''}
                  </p>
                </div>""", unsafe_allow_html=True)
        else:
            rows = [{
                "ID":         t["id"],
                "Title":      t["title"],
                "Platform":   t["platform"],
                "Status":     t["status"],
                "Priority":   t["priority"],
                "Progress %": t.get("progress", 0),
                "Requestor":  t.get("requestor", ""),
                "Due Date":   t.get("due_date", ""),
                "Created":    t.get("created_at", "")[:10],
            } for t in filtered]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════════════════════
# UPDATE TICKET
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Update Ticket":
    if not tickets:
        st.info("No tickets to update yet.")
    else:
        ticket_options = {f"{t['id']} - {t['title']}": i for i, t in enumerate(tickets)}
        selected_label = st.selectbox("Select Ticket", list(ticket_options.keys()))
        idx = ticket_options[selected_label]
        t   = st.session_state.tickets[idx]

        st.markdown(f"""
        <div class="ticket-card">
          <div class="ticket-id">{t['id']} · Created {t.get('created_at','')[:10]} · Requestor: {t.get('requestor','')}</div>
          <div class="ticket-title">{t['title']}</div>
          <div class="pills">
            {badge(t['platform'], PLATFORM_COLORS.get(t['platform'], DHL_GRAY))}
            {badge(t['status'],   STATUS_COLORS.get(t['status'],     DHL_GRAY))}
            {badge(t['priority'], PRIORITY_COLORS.get(t['priority'], DHL_GRAY))}
          </div>
          <p style="color:{DHL_GRAY};font-size:14px;margin-top:8px">{t.get('description','')}</p>
        </div>""", unsafe_allow_html=True)

        st.markdown("#### Update Fields")
        uc1, uc2, uc3 = st.columns(3)
        with uc1: new_status   = st.selectbox("Status",   STATUS_ORDER,   index=STATUS_ORDER.index(t["status"]))
        with uc2: new_priority = st.selectbox("Priority", PRIORITY_ORDER, index=PRIORITY_ORDER.index(t["priority"]))
        with uc3: new_progress = st.slider("Progress %", 0, 100, t.get("progress", 0), step=5)

        new_comment = st.text_area("Add Comment / Note", placeholder="Describe progress, blockers, or updates...")

        if st.button("Save and Sync to GitHub"):
            updated = list(st.session_state.tickets)
            updated[idx]["status"]     = new_status
            updated[idx]["priority"]   = new_priority
            updated[idx]["progress"]   = new_progress
            updated[idx]["updated_at"] = datetime.now().isoformat()
            if new_comment.strip():
                updated[idx].setdefault("comments", []).append({
                    "text":      new_comment.strip(),
                    "timestamp": datetime.now().isoformat(),
                })
            with st.spinner("Syncing to GitHub..."):
                save_and_sync(updated)
            st.success("Ticket updated and saved to GitHub.")
            st.rerun()

        comments = t.get("comments", [])
        if comments:
            st.markdown("#### Comment History")
            for c in reversed(comments):
                st.markdown(f"""
                <div style="background:{DHL_LIGHT};border:1px solid {DHL_BORDER};border-left:4px solid {DHL_YELLOW};
                            border-radius:6px;padding:12px 16px;margin-bottom:8px">
                  <p style="color:{DHL_GRAY};font-size:11px;font-weight:600;margin:0 0 6px;text-transform:uppercase;letter-spacing:.05em">
                    {c['timestamp'][:16].replace('T', ' at ')}
                  </p>
                  <p style="color:{DHL_DARK};margin:0;font-size:14px">{c['text']}</p>
                </div>""", unsafe_allow_html=True)

        st.markdown("---")
        with st.expander("Danger Zone"):
            st.warning("This will permanently delete this ticket from GitHub.")
            if st.button("Delete This Ticket", type="secondary"):
                updated = [tk for i, tk in enumerate(st.session_state.tickets) if i != idx]
                with st.spinner("Deleting..."):
                    save_and_sync(updated)
                st.success("Ticket deleted.")
                st.rerun()
