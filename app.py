import streamlit as st
import pandas as pd
import io
import base64
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, date
import uuid
import plotly.express as px
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="QA Viz Tracker", layout="wide",
                   initial_sidebar_state="expanded")

# ─────────────────────────────────────────────────────────────────────────────
# GITHUB CONFIG
# ─────────────────────────────────────────────────────────────────────────────
GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
GITHUB_REPO  = st.secrets["GITHUB_REPO"]
FILE_PATH    = "tickets.csv"
BRANCH       = "main"
GITHUB_API   = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{FILE_PATH}"
GH_HEADERS   = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

# ─────────────────────────────────────────────────────────────────────────────
# USERS  (stored in Streamlit secrets)
# secrets.toml format:
#   [users]
#   serol   = "1234"
#   ahmad   = "5678"
#   nurul   = "9012"
#   razif   = "3456"
# ─────────────────────────────────────────────────────────────────────────────
USERS: dict = dict(st.secrets.get("users", {}))

# ─────────────────────────────────────────────────────────────────────────────
# CSV SCHEMA  — every action appends one row; nothing is ever overwritten
# ─────────────────────────────────────────────────────────────────────────────
CSV_COLS = [
    "timestamp",   # ISO datetime of the action
    "action",      # CREATED | UPDATED | DELETED
    "ticket_id",   # QA-XXXXXX
    "title",
    "platform",    # Splunk | Power BI | Others
    "priority",    # Low | Medium | High | Critical
    "status",      # Backlog | In Progress | In Review | Blocked | Done
    "progress",    # 0-100
    "requestor",   # person who raised the original request
    "due_date",
    "tags",        # comma-separated
    "description",
    "updated_by",  # username (logged-in) or "Guest:<name>" (public submit)
    "notes",       # comment added with this action
]

# ─────────────────────────────────────────────────────────────────────────────
# GITHUB HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def gh_load() -> tuple[pd.DataFrame, str | None]:
    """Pull tickets.csv from GitHub. Returns (dataframe, sha)."""
    r = requests.get(GITHUB_API, headers=GH_HEADERS)
    if r.status_code == 404:
        return pd.DataFrame(columns=CSV_COLS), None
    r.raise_for_status()
    data    = r.json()
    content = base64.b64decode(data["content"]).decode("utf-8")
    df = pd.read_csv(io.StringIO(content), dtype=str).fillna("")
    # ensure all expected columns exist
    for col in CSV_COLS:
        if col not in df.columns:
            df[col] = ""
    return df[CSV_COLS], data["sha"]

def gh_append(new_row: dict) -> None:
    """Append one row to tickets.csv and push to GitHub."""
    df, sha = gh_load()
    updated = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    csv_bytes = updated.to_csv(index=False).encode("utf-8")
    payload = {
        "message": (f"[{new_row['action']}] {new_row['ticket_id']} "
                    f"by {new_row['updated_by']} — {new_row['timestamp'][:16]}"),
        "content": base64.b64encode(csv_bytes).decode("utf-8"),
        "branch":  BRANCH,
    }
    if sha:
        payload["sha"] = sha
    r = requests.put(GITHUB_API, headers=GH_HEADERS, json=payload)
    r.raise_for_status()
    # refresh session cache
    st.session_state.log_df = updated

def current_tickets(df: pd.DataFrame) -> pd.DataFrame:
    """
    Derive the current state of every ticket by taking the
    latest CREATED/UPDATED row per ticket_id, then removing DELETED ones.
    """
    if df.empty:
        return pd.DataFrame(columns=CSV_COLS)
    active  = df[df["action"].isin(["CREATED", "UPDATED"])].copy()
    if active.empty:
        return pd.DataFrame(columns=CSV_COLS)
    active["progress"] = pd.to_numeric(active["progress"], errors="coerce").fillna(0).astype(int)
    latest  = (active.sort_values("timestamp")
                     .groupby("ticket_id", as_index=False)
                     .last())
    deleted = set(df[df["action"] == "DELETED"]["ticket_id"].tolist())
    return latest[~latest["ticket_id"].isin(deleted)].reset_index(drop=True)

# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE BOOTSTRAP
# ─────────────────────────────────────────────────────────────────────────────
if "log_df" not in st.session_state:
    with st.spinner("Loading from GitHub..."):
        try:
            st.session_state.log_df, _ = gh_load()
        except Exception as e:
            st.error(f"Could not reach GitHub: {e}")
            st.session_state.log_df = pd.DataFrame(columns=CSV_COLS)

if "logged_in_user" not in st.session_state:
    st.session_state.logged_in_user = None   # None = not logged in

if "show_login_form" not in st.session_state:
    st.session_state.show_login_form = False

# ─────────────────────────────────────────────────────────────────────────────
# COLOURS & CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
DHL_YELLOW = "#FFCC00"
DHL_RED    = "#D40511"
DHL_DARK   = "#1A1A1A"
DHL_GRAY   = "#6B6B6B"
DHL_LIGHT  = "#F5F5F5"
DHL_BORDER = "#E0E0E0"
DHL_WHITE  = "#FFFFFF"

PLATFORM_COLORS = {"Splunk": DHL_RED, "Power BI": "#0078D4", "Others": DHL_GRAY}
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
PRIORITY_ORDER   = ["Low", "Medium", "High", "Critical"]
COMPLEXITY_ORDER = ["Simple", "Medium", "Complex", "Critical"]
COMPLEXITY_COLORS = {
    "Simple":   "#2E7D32",
    "Medium":   "#0078D4",
    "Complex":  "#FF8C00",
    "Critical": "#6A0DAD",
}
STATUS_ORDER   = ["Backlog", "In Progress", "In Review", "Blocked", "Done"]

def badge(label, bg, fg="#fff"):
    return (f'<span style="background:{bg};color:{fg};padding:3px 12px;'
            f'border-radius:4px;font-size:12px;font-weight:700">{label}</span>')

def progress_bar(pct, color=DHL_YELLOW):
    pct = int(float(pct)) if str(pct).replace('.','',1).isdigit() else 0
    return (
        '<div style="background:#E0E0E0;border-radius:4px;height:12px;'
        'width:100%;overflow:hidden;margin:6px 0 2px">'
        '<div style="background:' + color + ';width:' + str(pct) + '%;height:100%;border-radius:4px"></div></div>'
        '<small style="color:#6B6B6B;font-size:12px">' + str(pct) + '% complete</small>'
    )


# ─────────────────────────────────────────────────────────────────────────────
# EMAIL NOTIFICATION
# ─────────────────────────────────────────────────────────────────────────────
def send_new_ticket_email(ticket: dict) -> None:
    """Send email notification when a new ticket is submitted."""
    try:
        gmail_user     = st.secrets["GMAIL_USER"]
        gmail_password = st.secrets["GMAIL_APP_PASSWORD"]
        notify_email   = st.secrets["NOTIFY_EMAIL"]
    except KeyError:
        return  # email not configured, skip silently

    subject = f"[QA Tracker] New Ticket: {ticket['ticket_id']} — {ticket['title']}"

    html = f"""
    <html><body style="font-family:Arial,sans-serif;background:#f5f5f5;padding:20px">
    <div style="max-width:600px;margin:auto;background:#fff;border-radius:8px;
                border-top:5px solid #FFCC00;padding:28px 32px;box-shadow:0 2px 8px rgba(0,0,0,.08)">
      <div style="font-size:22px;font-weight:900;color:#D40511;letter-spacing:1px;margin-bottom:4px">DHL</div>
      <div style="font-size:18px;font-weight:700;color:#1A1A1A;margin-bottom:20px">New QA Ticket Submitted</div>
      <table style="width:100%;border-collapse:collapse;font-size:14px">
        <tr style="background:#FFCC00">
          <td style="padding:10px 14px;font-weight:700;color:#1A1A1A;width:35%">Ticket ID</td>
          <td style="padding:10px 14px;font-weight:700;color:#1A1A1A">{ticket['ticket_id']}</td>
        </tr>
        <tr style="background:#f9f9f9">
          <td style="padding:10px 14px;color:#6B6B6B;font-weight:600">Title</td>
          <td style="padding:10px 14px;color:#1A1A1A">{ticket['title']}</td>
        </tr>
        <tr>
          <td style="padding:10px 14px;color:#6B6B6B;font-weight:600">Platform</td>
          <td style="padding:10px 14px;color:#1A1A1A">{ticket['platform']}</td>
        </tr>
        <tr style="background:#f9f9f9">
          <td style="padding:10px 14px;color:#6B6B6B;font-weight:600">Priority</td>
          <td style="padding:10px 14px;color:#1A1A1A">{ticket['priority']}</td>
        </tr>
        <tr>
          <td style="padding:10px 14px;color:#6B6B6B;font-weight:600">Requestor</td>
          <td style="padding:10px 14px;color:#1A1A1A">{ticket['requestor']}</td>
        </tr>
        <tr style="background:#f9f9f9">
          <td style="padding:10px 14px;color:#6B6B6B;font-weight:600">Due Date</td>
          <td style="padding:10px 14px;color:#1A1A1A">{ticket['due_date']}</td>
        </tr>
        <tr>
          <td style="padding:10px 14px;color:#6B6B6B;font-weight:600">Submitted By</td>
          <td style="padding:10px 14px;color:#1A1A1A">{ticket['updated_by']}</td>
        </tr>
        <tr style="background:#f9f9f9">
          <td style="padding:10px 14px;color:#6B6B6B;font-weight:600">Description</td>
          <td style="padding:10px 14px;color:#1A1A1A">{ticket['description']}</td>
        </tr>
        <tr>
          <td style="padding:10px 14px;color:#6B6B6B;font-weight:600">Notes</td>
          <td style="padding:10px 14px;color:#1A1A1A">{ticket.get('notes','—')}</td>
        </tr>
        <tr style="background:#f9f9f9">
          <td style="padding:10px 14px;color:#6B6B6B;font-weight:600">Submitted At</td>
          <td style="padding:10px 14px;color:#1A1A1A">{ticket['timestamp'][:16].replace('T', ' at ')}</td>
        </tr>
      </table>
      <div style="margin-top:24px;font-size:12px;color:#9E9E9E;border-top:1px solid #E0E0E0;padding-top:14px">
        This is an automated notification from your QA Viz Tracker.
      </div>
    </div>
    </body></html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = gmail_user
    msg["To"]      = notify_email
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, notify_email, msg.as_string())

# ─────────────────────────────────────────────────────────────────────────────
# EXCEL EXPORT
# ─────────────────────────────────────────────────────────────────────────────
def build_excel(log_df: pd.DataFrame) -> bytes:
    def h(c): return c.lstrip("#")
    def thin():
        s = Side(style="thin", color="E0E0E0")
        return Border(left=s, right=s, top=s, bottom=s)
    def hdr(ws, row, col, val, bg, fg="FFFFFF", merge_to=None, ht=None):
        c = ws.cell(row=row, column=col, value=val)
        c.fill = PatternFill("solid", start_color=bg)
        c.font = Font(bold=True, color=fg, name="Arial", size=10)
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = thin()
        if merge_to:
            ws.merge_cells(f"{get_column_letter(col)}{row}:{get_column_letter(merge_to)}{row}")
        if ht:
            ws.row_dimensions[row].height = ht
        return c

    wb = Workbook()

    # ── Sheet 1: Full Audit Log ───────────────────────────────────────────────
    ws1 = wb.active
    ws1.title = "Audit Log"
    ws1.sheet_view.showGridLines = False

    hdr(ws1, 1, 1, "QA VIZ TRACKER — FULL AUDIT LOG",
        h(DHL_YELLOW), h(DHL_DARK), merge_to=len(CSV_COLS), ht=34)
    ws1["A1"].font = Font(bold=True, color=h(DHL_DARK), name="Arial", size=13)
    hdr(ws1, 2, 1,
        f"Generated: {datetime.now().strftime('%d %B %Y %H:%M')}  |  Total rows: {len(log_df)}",
        h(DHL_DARK), h(DHL_YELLOW), merge_to=len(CSV_COLS), ht=18)
    ws1["A2"].font = Font(italic=True, color=h(DHL_YELLOW), name="Arial", size=10)
    ws1.row_dimensions[3].height = 5

    col_widths = [20, 10, 14, 32, 12, 12, 14, 10, 16, 14, 20, 40, 16, 30]
    for i, (col, w) in enumerate(zip(CSV_COLS, col_widths), 1):
        hdr(ws1, 4, i, col.upper().replace("_", " "), h(DHL_RED), "FFFFFF")
        ws1.column_dimensions[get_column_letter(i)].width = w
    ws1.row_dimensions[4].height = 22
    ws1.freeze_panes = "A5"

    action_colors = {"CREATED": "2E7D32", "UPDATED": "0078D4", "DELETED": "D40511"}
    for r, (_, row) in enumerate(log_df.iterrows(), 5):
        bg = "FFFFFF" if r % 2 == 1 else "F5F5F5"
        ws1.row_dimensions[r].height = 18
        for ci, col in enumerate(CSV_COLS, 1):
            val = row.get(col, "")
            cell = ws1.cell(row=r, column=ci, value=val)
            cell.border = thin()
            cell.font   = Font(name="Arial", size=10, color=h(DHL_DARK))
            cell.fill   = PatternFill("solid", start_color=bg)
            cell.alignment = Alignment(vertical="center", wrap_text=(ci == 12))
            if ci == 2:  # action column
                ac = action_colors.get(str(val), h(DHL_GRAY))
                cell.fill = PatternFill("solid", start_color=ac)
                cell.font = Font(name="Arial", size=10, color="FFFFFF", bold=True)
                cell.alignment = Alignment(horizontal="center", vertical="center")

    # ── Sheet 2: Current Tickets ──────────────────────────────────────────────
    ws2 = wb.create_sheet("Current Tickets")
    ws2.sheet_view.showGridLines = False

    latest = current_tickets(log_df)
    hdr(ws2, 1, 1, "CURRENT TICKET STATUS",
        h(DHL_YELLOW), h(DHL_DARK), merge_to=11, ht=34)
    ws2["A1"].font = Font(bold=True, color=h(DHL_DARK), name="Arial", size=13)
    hdr(ws2, 2, 1,
        f"Snapshot: {datetime.now().strftime('%d %B %Y %H:%M')}  |  Active tickets: {len(latest)}",
        h(DHL_DARK), h(DHL_YELLOW), merge_to=11, ht=18)
    ws2["A2"].font = Font(italic=True, color=h(DHL_YELLOW), name="Arial", size=10)
    ws2.row_dimensions[3].height = 5

    show_cols   = ["ticket_id","title","platform","priority","status",
                   "progress","requestor","due_date","tags","updated_by","timestamp"]
    show_widths = [14, 34, 12, 12, 14, 11, 16, 14, 22, 16, 20]
    for i, (col, w) in enumerate(zip(show_cols, show_widths), 1):
        hdr(ws2, 4, i, col.upper().replace("_"," "), h(DHL_RED), "FFFFFF")
        ws2.column_dimensions[get_column_letter(i)].width = w
    ws2.row_dimensions[4].height = 22
    ws2.freeze_panes = "A5"

    for r, (_, row) in enumerate(latest.iterrows(), 5):
        bg = "FFFFFF" if r % 2 == 1 else "F5F5F5"
        ws2.row_dimensions[r].height = 18
        for ci, col in enumerate(show_cols, 1):
            val = row.get(col, "")
            cell = ws2.cell(row=r, column=ci, value=str(val))
            cell.border = thin()
            cell.font   = Font(name="Arial", size=10, color=h(DHL_DARK))
            cell.fill   = PatternFill("solid", start_color=bg)
            cell.alignment = Alignment(vertical="center")
            if col == "platform":
                cell.fill = PatternFill("solid", start_color=h(PLATFORM_COLORS.get(val, DHL_GRAY)))
                cell.font = Font(name="Arial", size=10, color="FFFFFF", bold=True)
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col == "priority":
                cell.fill = PatternFill("solid", start_color=h(PRIORITY_COLORS.get(val, DHL_GRAY)))
                cell.font = Font(name="Arial", size=10, color="FFFFFF", bold=True)
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col == "status":
                cell.fill = PatternFill("solid", start_color=h(STATUS_COLORS.get(val, DHL_GRAY)))
                cell.font = Font(name="Arial", size=10, color="FFFFFF", bold=True)
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col == "progress":
                cell.value = int(val) if str(val).isdigit() else 0
                cell.number_format = '0"%"'
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.fill = PatternFill("solid", start_color=bg)

    # ── Sheet 3: Summary ─────────────────────────────────────────────────────
    ws3 = wb.create_sheet("Summary")
    ws3.sheet_view.showGridLines = False
    for col, w in zip("ABCD", [22, 12, 14, 14]):
        ws3.column_dimensions[col].width = w

    hdr(ws3, 1, 1, "SUMMARY", h(DHL_YELLOW), h(DHL_DARK), merge_to=4, ht=30)
    ws3["A1"].font = Font(bold=True, color=h(DHL_DARK), name="Arial", size=13)
    hdr(ws3, 2, 1, f"As of {datetime.now().strftime('%d %B %Y')}",
        h(DHL_DARK), h(DHL_YELLOW), merge_to=4, ht=18)
    ws3["A2"].font = Font(italic=True, color=h(DHL_YELLOW), name="Arial", size=10)

    def summary_block(ws, start, title, counts, color_map, order):
        hdr(ws, start, 1, title, h(DHL_RED), "FFFFFF", merge_to=4, ht=20)
        for ci, lbl in enumerate(["Category", "Count", "% of Total"], 1):
            hdr(ws, start+1, ci, lbl, h(DHL_DARK), "FFFFFF")
        ws.row_dimensions[start+1].height = 18
        r = start + 2
        total = sum(counts.values()) or 1
        for key in order:
            cnt = counts.get(key, 0)
            ca = ws.cell(row=r, column=1, value=key)
            ca.fill = PatternFill("solid", start_color=h(color_map.get(key, DHL_GRAY)))
            ca.font = Font(bold=True, color="FFFFFF", name="Arial", size=10)
            ca.alignment = Alignment(horizontal="center", vertical="center")
            ca.border = thin()
            cb = ws.cell(row=r, column=2, value=cnt)
            cb.font = Font(name="Arial", size=10, bold=True, color=h(DHL_DARK))
            cb.alignment = Alignment(horizontal="center"); cb.border = thin()
            cb.fill = PatternFill("solid", start_color="FFFFFF")
            cc = ws.cell(row=r, column=3, value=round(cnt/total*100, 1))
            cc.number_format = '0.0"%"'
            cc.font = Font(name="Arial", size=10, color=h(DHL_DARK))
            cc.alignment = Alignment(horizontal="center"); cc.border = thin()
            cc.fill = PatternFill("solid", start_color="F5F5F5")
            ws.row_dimensions[r].height = 20
            r += 1
        ct = ws.cell(row=r, column=1, value="TOTAL")
        ct.fill = PatternFill("solid", start_color=h(DHL_DARK))
        ct.font = Font(bold=True, color="FFFFFF", name="Arial")
        ct.alignment = Alignment(horizontal="center"); ct.border = thin()
        ctv = ws.cell(row=r, column=2, value=sum(counts.values()))
        ctv.fill = PatternFill("solid", start_color=h(DHL_YELLOW))
        ctv.font = Font(bold=True, name="Arial", color=h(DHL_DARK))
        ctv.alignment = Alignment(horizontal="center"); ctv.border = thin()
        ws.row_dimensions[r].height = 22
        return r + 2

    if not latest.empty:
        sc = dict(latest["status"].value_counts())
        pc = dict(latest["priority"].value_counts())
        pl = dict(latest["platform"].value_counts())
        nr = summary_block(ws3, 4,  "BY STATUS",   sc, STATUS_COLORS,   STATUS_ORDER)
        nr = summary_block(ws3, nr, "BY PRIORITY", pc, PRIORITY_COLORS, PRIORITY_ORDER)
        summary_block(ws3, nr, "BY PLATFORM", pl, PLATFORM_COLORS, ["Splunk","Power BI","Others"])

    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return out.getvalue()

# ─────────────────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap');
html,body,[class*="css"],.stApp{{font-family:'Roboto',sans-serif!important;background:{DHL_LIGHT}!important;color:{DHL_DARK}!important}}
.main .block-container{{background:{DHL_LIGHT};padding-top:1.2rem!important;max-width:1400px}}
[data-testid="stSidebar"]{{background:{DHL_DARK}!important;border-right:4px solid {DHL_YELLOW}!important}}
[data-testid="stSidebar"] *{{color:{DHL_WHITE}!important}}
[data-testid="stSidebar"] hr{{border-color:#444!important}}
.dhl-topbar{{background:{DHL_YELLOW};padding:12px 20px;border-radius:8px;margin-bottom:20px;
            border-left:6px solid {DHL_RED};display:flex;align-items:center;justify-content:space-between}}
.dhl-topbar h1{{margin:0;font-size:20px;font-weight:700;color:{DHL_DARK};text-transform:uppercase;letter-spacing:.5px}}
.dhl-topbar span{{font-size:12px;color:#555}}
.metric-card{{background:{DHL_WHITE};border:1px solid {DHL_BORDER};border-top:4px solid {DHL_YELLOW};
             border-radius:8px;padding:18px 20px;margin-bottom:8px;box-shadow:0 1px 4px rgba(0,0,0,.06)}}
.metric-card .val{{font-size:2.2rem;font-weight:700;color:{DHL_DARK};line-height:1;margin-bottom:4px}}
.metric-card .lbl{{font-size:12px;font-weight:600;color:{DHL_GRAY};text-transform:uppercase;letter-spacing:.06em}}
.metric-card.red{{border-top-color:{DHL_RED}}}
.metric-card.blue{{border-top-color:#0078D4}}
.metric-card.green{{border-top-color:#2E7D32}}
.metric-card.orange{{border-top-color:#FF8C00}}
.section-header{{font-size:17px;font-weight:700;color:{DHL_DARK};border-left:5px solid {DHL_YELLOW};
                padding-left:12px;margin:24px 0 14px;text-transform:uppercase;letter-spacing:.04em}}
.ticket-card{{background:{DHL_WHITE};border:1px solid {DHL_BORDER};border-left:5px solid {DHL_YELLOW};
             border-radius:8px;padding:15px 18px;margin-bottom:10px;box-shadow:0 1px 3px rgba(0,0,0,.05)}}
.ticket-card:hover{{border-left-color:{DHL_RED}}}
.ticket-id{{font-size:11px;font-weight:700;color:{DHL_GRAY};text-transform:uppercase;letter-spacing:.08em}}
.ticket-title{{font-size:15px;font-weight:700;color:{DHL_DARK};margin:4px 0 8px}}
.pills{{display:flex;gap:8px;flex-wrap:wrap;margin:6px 0 8px}}
.login-box{{background:{DHL_WHITE};border:1px solid {DHL_BORDER};border-top:4px solid {DHL_YELLOW};
           border-radius:8px;padding:20px;margin-bottom:16px}}
.user-chip{{background:{DHL_YELLOW};color:{DHL_DARK};padding:4px 14px;border-radius:20px;
           font-size:13px;font-weight:700;display:inline-block}}
.readonly-banner{{background:#FFF9E6;border:1px solid {DHL_YELLOW};border-radius:6px;
                 padding:8px 14px;font-size:13px;color:#7a6000;margin-bottom:12px}}
.stButton>button{{background:{DHL_YELLOW}!important;color:{DHL_DARK}!important;border:none!important;
                 border-radius:5px!important;font-weight:700!important;font-size:14px!important;padding:9px 22px!important}}
.stButton>button:hover{{background:{DHL_RED}!important;color:{DHL_WHITE}!important}}
.stTextInput>div>div>input,.stTextArea>div>div>textarea{{background:{DHL_WHITE}!important;
  color:{DHL_DARK}!important;border:1px solid {DHL_BORDER}!important;border-radius:5px!important}}
.stTextInput>div>div>input:focus,.stTextArea>div>div>textarea:focus{{border-color:{DHL_YELLOW}!important}}
.stSelectbox>div>div,.stMultiSelect>div>div{{background:{DHL_WHITE}!important;color:{DHL_DARK}!important}}
.stSlider>div>div>div>div{{background:{DHL_YELLOW}!important}}
#MainMenu,footer,header{{visibility:hidden}}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
user = st.session_state.logged_in_user  # None or username string

with st.sidebar:
    st.markdown("""
    <div style="padding:14px 0 6px">
      <div style="font-size:26px;font-weight:900;color:#FFCC00;letter-spacing:1px">DHL</div>
      <div style="font-size:12px;color:#aaa;margin-top:2px">QA Visualization Tracker</div>
    </div>""", unsafe_allow_html=True)

    # ── Login / user block ────────────────────────────────────────────────────
    st.markdown("---")
    if user:
        st.markdown(f'<div class="user-chip" style="background:#FFCC00;color:#1A1A1A;'
                    f'padding:5px 14px;border-radius:20px;font-size:13px;font-weight:700">'
                    f'Logged in as: {user}</div>', unsafe_allow_html=True)
        st.markdown("")
        if st.button("Logout"):
            st.session_state.logged_in_user = None
            st.session_state.show_login_form = False
            st.rerun()
    else:
        if not st.session_state.show_login_form:
            if st.button("Login"):
                st.session_state.show_login_form = True
                st.rerun()
        else:
            with st.form("login_form"):
                uname = st.text_input("Username")
                pin   = st.text_input("PIN", type="password")
                ok    = st.form_submit_button("Sign in")
            if ok:
                if uname in USERS and USERS[uname] == pin:
                    st.session_state.logged_in_user   = uname
                    st.session_state.show_login_form  = False
                    st.rerun()
                else:
                    st.error("Incorrect username or PIN.")

    st.markdown("---")

    # ── Navigation ────────────────────────────────────────────────────────────
    nav_options = ["Dashboard", "All Tickets", "Submit Request"]
    if user:
        nav_options += ["Update / Delete Ticket"]

    page = st.radio("Navigation", nav_options, label_visibility="collapsed")
    st.markdown("---")

    # ── Quick stats ───────────────────────────────────────────────────────────
    log_df  = st.session_state.log_df
    tickets = current_tickets(log_df)
    total   = len(tickets)
    done    = len(tickets[tickets["status"] == "Done"]) if not tickets.empty else 0
    blocked = len(tickets[tickets["status"] == "Blocked"]) if not tickets.empty else 0
    # My Tasks count for logged-in user
    if user and not tickets.empty:
        my_tasks = tickets[
            (tickets.get("assigned_to", pd.Series(dtype=str)) == user) &
            (~tickets["status"].isin(["Done"]))
        ] if "assigned_to" in tickets.columns else pd.DataFrame()
        my_count = len(my_tasks)
        my_blocked = len(my_tasks[my_tasks["status"] == "Blocked"]) if not my_tasks.empty else 0
        st.markdown(f"""
        <div style="background:#1e1e1e;border:1px solid #FFCC00;border-radius:6px;
                    padding:10px 14px;margin-bottom:10px">
          <div style="font-size:11px;color:#FFCC00;font-weight:700;text-transform:uppercase;
                      letter-spacing:.06em;margin-bottom:6px">My Tasks</div>
          <div style="font-size:22px;font-weight:900;color:#FFCC00;line-height:1">{my_count}</div>
          <div style="font-size:11px;color:#aaa;margin-top:2px">pending tickets assigned to you</div>
          {f'<div style="font-size:11px;color:#D40511;margin-top:4px;font-weight:700">{my_blocked} blocked</div>' if my_blocked else ""}
        </div>""", unsafe_allow_html=True)

    st.markdown(f"""
    <div style="font-size:13px;color:#ccc;line-height:2.2">
      <b style="color:#fff">Active tickets:</b> {total}<br>
      <b style="color:#FFCC00">Done:</b> {done}<br>
      <b style="color:#D40511">Blocked:</b> {blocked}
    </div>""", unsafe_allow_html=True)
    st.markdown("")

    # ── Export + Refresh ─────────────────────────────────────────────────────
    if not log_df.empty:
        excel_data = build_excel(log_df)
        st.download_button(
            "Download Excel Report",
            data=excel_data,
            file_name=f"QA_Tracker_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    st.markdown("")
    if st.button("Refresh from GitHub"):
        with st.spinner("Syncing..."):
            try:
                st.session_state.log_df, _ = gh_load()
                st.rerun()
            except Exception as e:
                st.error(str(e))

# Refresh local references after sidebar
log_df  = st.session_state.log_df
tickets = current_tickets(log_df)

# ── Plotly defaults ───────────────────────────────────────────────────────────
CHART = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor=DHL_WHITE,
    font=dict(color=DHL_DARK, family="Roboto"),
    title_font=dict(color=DHL_DARK, size=14),
    margin=dict(t=40, b=20, l=10, r=10),
)

# ─────────────────────────────────────────────────────────────────────────────
# PAGE HEADER helper
# ─────────────────────────────────────────────────────────────────────────────
PAGE_META = {
    "Dashboard":              ("Dashboard Overview",        "Live summary of all QA visualization requests"),
    "All Tickets":            ("All Tickets",               "Browse and filter every submitted ticket"),
    "Submit Request":         ("Submit New Request",        "Anyone can raise a new visualization request"),
    "Update / Delete Ticket": ("Update / Delete Ticket",   f"Editing as: {user}"),
}
title, subtitle = PAGE_META.get(page, ("QA Viz Tracker", ""))
st.markdown(f"""
<div class="dhl-topbar">
  <div><h1>{title}</h1><span>{subtitle}</span></div>
</div>""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# PAGE: DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────
if page == "Dashboard":
    df = tickets

    c1,c2,c3,c4,c5 = st.columns(5)
    for col, label, val, cls in [
        (c1, "Total Tickets",  len(df),                                                  ""),
        (c2, "In Progress",    len(df[df.status=="In Progress"]) if not df.empty else 0, "blue"),
        (c3, "In Review",      len(df[df.status=="In Review"])   if not df.empty else 0, "orange"),
        (c4, "Blocked",        len(df[df.status=="Blocked"])     if not df.empty else 0, "red"),
        (c5, "Done",           len(df[df.status=="Done"])        if not df.empty else 0, "green"),
    ]:
        with col:
            st.markdown(f'<div class="metric-card {cls}"><div class="val">{val}</div>'
                        f'<div class="lbl">{label}</div></div>', unsafe_allow_html=True)

    if df.empty:
        st.info("No tickets yet. Submit the first request using the sidebar.")
    else:
        st.markdown("---")
        r1a, r1b = st.columns(2)
        with r1a:
            sc = df["status"].value_counts().reset_index()
            sc.columns = ["Status","Count"]
            fig = px.pie(sc, names="Status", values="Count", hole=0.55,
                         title="By Status", color="Status", color_discrete_map=STATUS_COLORS)
            fig.update_layout(**CHART)
            st.plotly_chart(fig, use_container_width=True)
        with r1b:
            pc = df["platform"].value_counts().reset_index()
            pc.columns = ["Platform","Count"]
            fig2 = px.bar(pc, x="Platform", y="Count", title="By Platform",
                          color="Platform", color_discrete_map=PLATFORM_COLORS, text="Count")
            fig2.update_layout(**CHART, showlegend=False,
                               xaxis=dict(gridcolor=DHL_BORDER),
                               yaxis=dict(gridcolor=DHL_BORDER))
            fig2.update_traces(textposition="outside", marker_line_width=0)
            st.plotly_chart(fig2, use_container_width=True)

        r2a, r2b = st.columns(2)
        with r2a:
            prc = df["priority"].value_counts().reindex(PRIORITY_ORDER, fill_value=0).reset_index()
            prc.columns = ["Priority","Count"]
            fig3 = px.bar(prc, x="Priority", y="Count", title="By Priority",
                          color="Priority", color_discrete_map=PRIORITY_COLORS, text="Count")
            fig3.update_layout(**CHART, showlegend=False,
                               xaxis=dict(gridcolor=DHL_BORDER),
                               yaxis=dict(gridcolor=DHL_BORDER))
            fig3.update_traces(textposition="outside", marker_line_width=0)
            st.plotly_chart(fig3, use_container_width=True)
        with r2b:
            df["progress"] = pd.to_numeric(df["progress"], errors="coerce").fillna(0)
            ap = df.groupby("status")["progress"].mean().reset_index()
            ap.columns = ["Status","Avg"]
            fig4 = px.bar(ap, x="Status", y="Avg", title="Avg Progress % by Status",
                          color="Status", color_discrete_map=STATUS_COLORS,
                          text=ap["Avg"].round(1).astype(str)+"%")
            fig4.update_layout(**CHART, showlegend=False,
                               xaxis=dict(gridcolor=DHL_BORDER),
                               yaxis=dict(gridcolor=DHL_BORDER, range=[0,115]))
            fig4.update_traces(textposition="outside", marker_line_width=0)
            st.plotly_chart(fig4, use_container_width=True)

        # Activity timeline from audit log
        if not log_df.empty:
            st.markdown('<div class="section-header">Activity Timeline</div>',
                        unsafe_allow_html=True)
            tl = log_df.copy()
            tl["date"] = tl["timestamp"].str[:10]
            daily = tl.groupby(["date","action"]).size().reset_index(name="count")
            fig5 = px.bar(daily, x="date", y="count", color="action",
                          title="Daily Actions",
                          color_discrete_map={"CREATED":"#2E7D32",
                                              "UPDATED":"#0078D4",
                                              "DELETED":"#D40511"})
            fig5.update_layout(**CHART, xaxis=dict(gridcolor=DHL_BORDER),
                               yaxis=dict(gridcolor=DHL_BORDER))
            st.plotly_chart(fig5, use_container_width=True)

        st.markdown('<div class="section-header">Recent Tickets</div>',
                    unsafe_allow_html=True)
        recent = df.sort_values("timestamp", ascending=False).head(5)
        for _, t in recent.iterrows():
            pct = int(float(t.get("progress", 0) or 0))
            bc  = STATUS_COLORS.get(t["status"], DHL_YELLOW)
            tag_html = " ".join(
                f'<span style="background:{DHL_LIGHT};color:{DHL_DARK};border:1px solid {DHL_BORDER};'
                f'padding:1px 8px;border-radius:4px;font-size:11px;font-weight:600">{tg}</span>'
                for tg in str(t.get("tags","")).split(",") if tg.strip()
            )
            complexity_badge = badge("Complexity: " + str(t.get("complexity","")), "#555555") if t.get("complexity") else ""
            assigned_badge   = badge("Assigned: " + str(t.get("assigned_to","")), "#1A1A1A", DHL_YELLOW) if t.get("assigned_to") else ""
            ticket_id_val    = t["ticket_id"]
            requestor_val    = t.get("requestor","")
            due_val          = t.get("due_date","—")
            title_val        = t["title"]
            plat_badge       = badge(t["platform"],  PLATFORM_COLORS.get(t["platform"],  DHL_GRAY))
            stat_badge       = badge(t["status"],    STATUS_COLORS.get(t["status"],       DHL_GRAY))
            prio_badge       = badge(t["priority"],  PRIORITY_COLORS.get(t["priority"],   DHL_GRAY))
            st.markdown(
                '<div class="ticket-card">'
                + f'<div class="ticket-id">{ticket_id_val} · {requestor_val} · Due {due_val}</div>'
                + f'<div class="ticket-title">{title_val}</div>'
                + '<div class="pills">' + plat_badge + stat_badge + prio_badge + complexity_badge + assigned_badge + tag_html + '</div>'
                + progress_bar(pct, bc)
                + '</div>',
                unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# PAGE: ALL TICKETS
# ─────────────────────────────────────────────────────────────────────────────
elif page == "All Tickets":
    if tickets.empty:
        st.info("No tickets yet.")
    else:
        fc1,fc2,fc3,fc4 = st.columns(4)
        with fc1: fp = st.multiselect("Platform", ["Splunk","Power BI","Others"],
                                      default=["Splunk","Power BI","Others"])
        with fc2: fs = st.multiselect("Status",   STATUS_ORDER,   default=STATUS_ORDER)
        with fc3: fr = st.multiselect("Priority", PRIORITY_ORDER, default=PRIORITY_ORDER)
        with fc4: fq = st.text_input("Search", placeholder="title / requestor...")

        df = tickets
        df = df[df["platform"].isin(fp) & df["status"].isin(fs) & df["priority"].isin(fr)]
        if fq:
            mask = (df["title"].str.contains(fq, case=False, na=False) |
                    df["requestor"].str.contains(fq, case=False, na=False))
            df = df[mask]

        sc1,sc2 = st.columns([2,1])
        with sc1:
            sort_by = st.selectbox("Sort by", ["Newest first","Oldest first",
                                               "Priority (high to low)",
                                               "Progress (high to low)","Due Date"])
        with sc2:
            view_mode = st.radio("View", ["Cards","Table"], horizontal=True)

        def skey(row):
            if sort_by == "Newest first":           return row["timestamp"]
            if sort_by == "Oldest first":           return row["timestamp"]
            if sort_by == "Priority (high to low)": return PRIORITY_ORDER.index(row["priority"]) if row["priority"] in PRIORITY_ORDER else 99
            if sort_by == "Progress (high to low)": return -int(row["progress"]) if str(row["progress"]).isdigit() else 0
            return row.get("due_date","")

        df = df.copy()
        df["_sk"] = df.apply(skey, axis=1)
        df = df.sort_values("_sk", ascending=(sort_by not in ["Newest first","Progress (high to low)"]))
        st.caption(f"Showing {len(df)} ticket(s)")

        if view_mode == "Cards":
            for _, t in df.iterrows():
                pct = int(float(t.get("progress", 0) or 0))
                bc  = STATUS_COLORS.get(t["status"], DHL_YELLOW)
                tag_html = " ".join(
                    f'<span style="background:{DHL_LIGHT};color:{DHL_DARK};border:1px solid {DHL_BORDER};'
                    f'padding:1px 8px;border-radius:4px;font-size:11px;font-weight:600">{tg}</span>'
                    for tg in str(t.get("tags","")).split(",") if tg.strip()
                )
                desc       = str(t.get("description",""))
                desc_short = desc[:200] + ("..." if len(desc) > 200 else "")
                complexity_badge = badge("Complexity: " + str(t.get("complexity","")), "#555555") if t.get("complexity") else ""
                assigned_badge   = badge("Assigned: " + str(t.get("assigned_to","")), "#1A1A1A", DHL_YELLOW) if t.get("assigned_to") else ""
                ticket_id_val = t["ticket_id"]
                requestor_val = t.get("requestor","")
                due_val       = t.get("due_date","—")
                assigned_val  = t.get("assigned_to","Unassigned")
                updated_val   = t.get("updated_by","")
                title_val     = t["title"]
                plat_badge    = badge(t["platform"],  PLATFORM_COLORS.get(t["platform"],  DHL_GRAY))
                stat_badge    = badge(t["status"],    STATUS_COLORS.get(t["status"],       DHL_GRAY))
                prio_badge    = badge(t["priority"],  PRIORITY_COLORS.get(t["priority"],   DHL_GRAY))
                st.markdown(
                    '<div class="ticket-card">'
                    + f'<div class="ticket-id">{ticket_id_val} · {requestor_val} · Due {due_val} · Assigned: {assigned_val} · Updated by {updated_val}</div>'
                    + f'<div class="ticket-title">{title_val}</div>'
                    + '<div class="pills">' + plat_badge + stat_badge + prio_badge + complexity_badge + assigned_badge + tag_html + '</div>'
                    + progress_bar(pct, bc)
                    + f'<p style="color:#6B6B6B;font-size:13px;margin-top:6px">{desc_short}</p>'
                    + '</div>',
                    unsafe_allow_html=True)
        else:
            show = ["ticket_id","title","platform","priority","status","progress",
                    "requestor","due_date","updated_by","timestamp"]
            st.dataframe(df[show].rename(columns=lambda c: c.replace("_"," ").title()),
                         use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────────────────────────────────────
# PAGE: SUBMIT REQUEST  (open to everyone)
# ─────────────────────────────────────────────────────────────────────────────
elif page == "Submit Request":
    if not user:
        st.markdown(
            '<div class="readonly-banner">You are submitting as a guest. '
            'Login (top-left) to enable ticket updates and deletions.</div>',
            unsafe_allow_html=True)

    with st.form("submit_form", clear_on_submit=True):
        c1,c2 = st.columns(2)
        with c1:
            title_val    = st.text_input("Ticket Title *", placeholder="e.g. Sales Dashboard KPI refresh")
            platform_val = st.selectbox("Platform *", ["Splunk","Power BI","Others"])
            priority_val = st.selectbox("Priority *", PRIORITY_ORDER)
        with c2:
            # If logged in, pre-fill name but still allow editing
            default_name = user if user else ""
            requestor_val = st.text_input("Your Name *", value=default_name,
                                          placeholder="Enter your name")
            due_val  = st.date_input("Target Due Date", value=date.today())
            tags_val = st.text_input("Tags (comma-separated)", placeholder="e.g. kpi, finance, Q2")
        desc_val = st.text_area("Description / Requirements *",
                                placeholder="Describe the request in detail...", height=150)
        notes_val = st.text_input("Notes (optional)", placeholder="Any additional notes for this submission...")
        submitted = st.form_submit_button("Submit Ticket")

    if submitted:
        if not title_val or not requestor_val or not desc_val:
            st.error("Please fill in all required fields (*).")
        else:
            tid = "QA-" + str(uuid.uuid4())[:6].upper()
            updated_by = user if user else f"Guest:{requestor_val}"
            row = {
                "timestamp":   datetime.now().isoformat(timespec="seconds"),
                "action":      "CREATED",
                "ticket_id":   tid,
                "title":       title_val,
                "platform":    platform_val,
                "priority":    priority_val,
                "status":      "Backlog",
                "progress":    0,
                "requestor":   requestor_val,
                "due_date":    str(due_val),
                "tags":        ", ".join([t.strip() for t in tags_val.split(",") if t.strip()]),
                "description": desc_val,
                "updated_by":  updated_by,
                "notes":       notes_val,
            }
            with st.spinner("Saving to GitHub..."):
                try:
                    gh_append(row)
                    send_new_ticket_email(row)
                    st.success(f"Ticket **{tid}** submitted and logged to CSV.")
                    st.markdown(f"""<div class="ticket-card">
                      <div class="ticket-id">{tid}</div>
                      <div class="ticket-title">{title_val}</div>
                      <div class="pills">
                        {badge(platform_val, PLATFORM_COLORS.get(platform_val, DHL_GRAY))}
                        {badge('Backlog', STATUS_COLORS['Backlog'])}
                        {badge(priority_val, PRIORITY_COLORS.get(priority_val, DHL_GRAY))}
                      </div>
                      <small style="color:{DHL_GRAY}">Logged by: {updated_by}</small>
                    </div>""", unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"GitHub sync failed: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# PAGE: UPDATE / DELETE  (logged-in only)
# ─────────────────────────────────────────────────────────────────────────────
elif page == "Update / Delete Ticket":
    if not user:
        st.warning("You must be logged in to update or delete tickets.")
    elif tickets.empty:
        st.info("No tickets found.")
    else:
        options = {f"{r['ticket_id']} - {r['title']}": r['ticket_id']
                   for _, r in tickets.iterrows()}
        sel_label = st.selectbox("Select Ticket", list(options.keys()))
        sel_id    = options[sel_label]
        t         = tickets[tickets["ticket_id"] == sel_id].iloc[0]

        # Show current state
        pct = int(float(t.get("progress", 0) or 0))
        complexity_badge = badge("Complexity: " + str(t.get("complexity","")), "#555555") if t.get("complexity") else ""
        assigned_badge   = badge("Assigned: " + str(t.get("assigned_to","Unassigned")), "#1A1A1A", DHL_YELLOW) if t.get("assigned_to") else badge("Unassigned", "#9E9E9E")
        ticket_id_val = t["ticket_id"]
        requestor_val = t.get("requestor","")
        due_val       = t.get("due_date","")
        title_val     = t["title"]
        desc_val      = t.get("description","")
        plat_badge    = badge(t["platform"],  PLATFORM_COLORS.get(t["platform"],  DHL_GRAY))
        stat_badge    = badge(t["status"],    STATUS_COLORS.get(t["status"],       DHL_GRAY))
        prio_badge    = badge(t["priority"],  PRIORITY_COLORS.get(t["priority"],   DHL_GRAY))
        st.markdown(
            '<div class="ticket-card">'
            + f'<div class="ticket-id">{ticket_id_val} · Requestor: {requestor_val} · Due: {due_val}</div>'
            + f'<div class="ticket-title">{title_val}</div>'
            + '<div class="pills">' + plat_badge + stat_badge + prio_badge + complexity_badge + assigned_badge + '</div>'
            + progress_bar(pct, STATUS_COLORS.get(t["status"], DHL_YELLOW))
            + f'<p style="color:#6B6B6B;font-size:13px;margin-top:6px">{desc_val}</p>'
            + '</div>',
            unsafe_allow_html=True)

        st.markdown("#### Update Fields")
        uc1,uc2,uc3 = st.columns(3)
        cur_status     = t["status"]     if t["status"]     in STATUS_ORDER     else STATUS_ORDER[0]
        cur_priority   = t["priority"]   if t["priority"]   in PRIORITY_ORDER   else PRIORITY_ORDER[0]
        cur_complexity = t.get("complexity","") if t.get("complexity","") in COMPLEXITY_ORDER else COMPLEXITY_ORDER[0]
        with uc1: new_status     = st.selectbox("Status",     STATUS_ORDER,
                                                 index=STATUS_ORDER.index(cur_status))
        with uc2: new_priority   = st.selectbox("Priority",   PRIORITY_ORDER,
                                                 index=PRIORITY_ORDER.index(cur_priority))
        with uc3: new_progress   = st.slider("Progress %", 0, 100, pct, step=5)

        uc4,uc5 = st.columns(2)
        user_list = list(USERS.keys())
        cur_assigned = t.get("assigned_to","") if t.get("assigned_to","") in user_list else user_list[0]
        with uc4: new_complexity = st.selectbox("Complexity", COMPLEXITY_ORDER,
                                                 index=COMPLEXITY_ORDER.index(cur_complexity))
        with uc5: new_assigned   = st.selectbox("Assign To",  user_list,
                                                 index=user_list.index(cur_assigned) if cur_assigned in user_list else 0)

        new_notes = st.text_area("Notes / Comment *",
                                 placeholder="Describe what changed or why...")

        if st.button("Save Update"):
            if not new_notes.strip():
                st.error("Please add a note describing the update.")
            else:
                row = {
                    "timestamp":   datetime.now().isoformat(timespec="seconds"),
                    "action":      "UPDATED",
                    "ticket_id":   sel_id,
                    "title":       t["title"],
                    "platform":    t["platform"],
                    "priority":    new_priority,
                    "status":      new_status,
                    "progress":    new_progress,
                    "requestor":   t["requestor"],
                    "due_date":    t["due_date"],
                    "tags":        t["tags"],
                    "description": t["description"],
                    "updated_by":  user,
                    "notes":       new_notes.strip(),
                    "complexity":  new_complexity,
                    "assigned_to": new_assigned,
                }
                with st.spinner("Saving to GitHub..."):
                    try:
                        gh_append(row)
                        st.success(f"Ticket {sel_id} updated and logged to CSV.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"GitHub sync failed: {e}")

        # History for this ticket
        ticket_log = log_df[log_df["ticket_id"] == sel_id].sort_values("timestamp", ascending=False)
        if not ticket_log.empty:
            st.markdown("#### History for this ticket")
            for _, row in ticket_log.iterrows():
                action_color = {"CREATED":"#2E7D32","UPDATED":"#0078D4","DELETED":"#D40511"}
                ac = row["action"]
                st.markdown(f"""
                <div style="background:{DHL_LIGHT};border:1px solid {DHL_BORDER};
                            border-left:4px solid {action_color.get(ac, DHL_GRAY)};
                            border-radius:6px;padding:10px 14px;margin-bottom:8px">
                  <div style="display:flex;gap:12px;align-items:center;margin-bottom:4px">
                    {badge(ac, action_color.get(ac, DHL_GRAY))}
                    <span style="font-size:12px;color:{DHL_GRAY}">{row['timestamp'][:16].replace('T',' at ')}</span>
                    <span style="font-size:12px;font-weight:700;color:{DHL_DARK}">by {row['updated_by']}</span>
                  </div>
                  <div style="font-size:13px;color:{DHL_DARK}">
                    Status: <b>{row['status']}</b> &nbsp;|&nbsp;
                    Priority: <b>{row['priority']}</b> &nbsp;|&nbsp;
                    Progress: <b>{row['progress']}%</b> &nbsp;|&nbsp;
                    Complexity: <b>{row.get('complexity','—')}</b> &nbsp;|&nbsp;
                    Assigned: <b>{row.get('assigned_to','—')}</b>
                  </div>
                  {f'<div style="font-size:13px;color:{DHL_GRAY};margin-top:4px">{row["notes"]}</div>' if row.get("notes") else ""}
                </div>""", unsafe_allow_html=True)

        # Delete
        st.markdown("---")
        with st.expander("Danger Zone"):
            st.warning("This logs a DELETED action. The ticket will be removed from the active view but the full history is preserved in the CSV.")
            del_note = st.text_input("Reason for deletion *")
            if st.button("Delete Ticket", type="secondary"):
                if not del_note.strip():
                    st.error("Please provide a reason for deletion.")
                else:
                    row = {
                        "timestamp":   datetime.now().isoformat(timespec="seconds"),
                        "action":      "DELETED",
                        "ticket_id":   sel_id,
                        "title":       t["title"],
                        "platform":    t["platform"],
                        "priority":    t["priority"],
                        "status":      t["status"],
                        "progress":    t["progress"],
                        "requestor":   t["requestor"],
                        "due_date":    t["due_date"],
                        "tags":        t["tags"],
                        "description": t["description"],
                        "updated_by":  user,
                        "notes":       del_note.strip(),
                    }
                    with st.spinner("Logging deletion..."):
                        try:
                            gh_append(row)
                            st.success("Ticket deleted from active view. History preserved in CSV.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"GitHub sync failed: {e}")
