import streamlit as st
import pandas as pd
import json
import base64
import requests
from datetime import datetime, date
import uuid
import plotly.express as px

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="QA Viz Tracker",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── GitHub config (from Streamlit secrets) ────────────────────────────────────
GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
GITHUB_REPO  = st.secrets["GITHUB_REPO"]   # e.g. "yourname/qa-tracker"
FILE_PATH    = "tickets.json"
BRANCH       = "main"

GITHUB_API   = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{FILE_PATH}"
HEADERS      = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

# ── GitHub helpers ─────────────────────────────────────────────────────────────
def gh_load():
    """Load tickets from GitHub. Returns (tickets_list, sha)."""
    r = requests.get(GITHUB_API, headers=HEADERS)
    if r.status_code == 404:
        return [], None
    r.raise_for_status()
    data    = r.json()
    content = base64.b64decode(data["content"]).decode("utf-8")
    return json.loads(content), data["sha"]

def gh_save(tickets, sha):
    """Push updated tickets list to GitHub."""
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

# ── Session state bootstrap ───────────────────────────────────────────────────
if "tickets" not in st.session_state:
    with st.spinner("Loading tickets from GitHub…"):
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

# ── Constants ─────────────────────────────────────────────────────────────────
PLATFORM_COLORS = {"Splunk": "#ff6b35", "Power BI": "#f2c811"}
STATUS_COLORS   = {
    "Backlog":     "#64748b",
    "In Progress": "#3b82f6",
    "In Review":   "#a855f7",
    "Done":        "#22c55e",
    "Blocked":     "#ef4444",
}
PRIORITY_COLORS = {"Low":"#22c55e","Medium":"#f59e0b","High":"#ef4444","Critical":"#7c3aed"}
PRIORITY_ORDER  = ["Low","Medium","High","Critical"]
STATUS_ORDER    = ["Backlog","In Progress","In Review","Blocked","Done"]

def badge(label, color, text_color="#fff"):
    return (f'<span style="background:{color};color:{text_color};padding:2px 10px;'
            f'border-radius:20px;font-size:12px;font-weight:700">{label}</span>')

def progress_bar_html(pct, color="#3b82f6"):
    return (
        f'<div style="background:#1e293b;border-radius:8px;height:10px;width:100%;overflow:hidden">'
        f'<div style="background:{color};width:{pct}%;height:100%;border-radius:8px"></div></div>'
        f'<small style="color:#94a3b8">{pct}% complete</small>'
    )

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');
html,body,[class*="css"]{font-family:'Space Grotesk',sans-serif;background:#0a0f1e;color:#e2e8f0}
[data-testid="stSidebar"]{background:#0d1427!important;border-right:1px solid #1e293b}
[data-testid="stSidebar"] *{color:#cbd5e1!important}
.metric-card{background:linear-gradient(135deg,#111827,#1e293b);border:1px solid #1e3a5f;border-radius:16px;padding:20px 24px;margin-bottom:8px}
.metric-card h1{font-family:'JetBrains Mono',monospace;font-size:2.4rem;margin:0}
.metric-card p{color:#64748b;font-size:13px;margin:4px 0 0;text-transform:uppercase;letter-spacing:.05em}
.ticket-card{background:#111827;border:1px solid #1e293b;border-left:4px solid #3b82f6;border-radius:12px;padding:16px 20px;margin-bottom:12px}
.ticket-id{font-family:'JetBrains Mono',monospace;font-size:11px;color:#475569}
.ticket-title{font-size:16px;font-weight:600;margin:4px 0 8px;color:#f1f5f9}
.section-header{font-size:22px;font-weight:700;color:#f1f5f9;border-bottom:2px solid #1e3a5f;padding-bottom:10px;margin:24px 0 16px}
.pills{display:flex;gap:8px;flex-wrap:wrap;margin:6px 0 10px}
.sync-badge{background:#0d2137;border:1px solid #1e3a5f;border-radius:8px;padding:6px 14px;font-size:12px;color:#60a5fa;display:inline-block;margin-bottom:8px}
.stButton>button{background:linear-gradient(135deg,#1d4ed8,#3b82f6);color:#fff;border:none;border-radius:10px;font-weight:700;padding:10px 24px;font-size:14px}
.stTextInput>div>div>input,.stTextArea>div>div>textarea,.stSelectbox>div>div{background:#111827!important;color:#e2e8f0!important;border-color:#1e3a5f!important;border-radius:10px!important}
#MainMenu,footer,header{visibility:hidden}
.block-container{padding-top:1.5rem!important}
</style>
""", unsafe_allow_html=True)

tickets = st.session_state.tickets

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📊 QA Viz Tracker")
    st.markdown('<div class="sync-badge">☁️ Synced · GitHub</div>', unsafe_allow_html=True)
    st.markdown("---")
    page = st.radio("Navigation", [
        "🏠 Dashboard","➕ Submit Request","📋 All Tickets","✏️ Update Ticket"
    ], label_visibility="collapsed")
    st.markdown("---")
    total   = len(tickets)
    done    = sum(1 for t in tickets if t["status"]=="Done")
    blocked = sum(1 for t in tickets if t["status"]=="Blocked")
    st.markdown(f"**Total:** {total} &nbsp;|&nbsp; ✅ {done} &nbsp;|&nbsp; 🔴 {blocked}")
    if st.button("🔄 Refresh"):
        with st.spinner("Syncing…"):
            try:
                st.session_state.tickets, st.session_state.gh_sha = gh_load()
                st.rerun()
            except Exception as e:
                st.error(str(e))

# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
if page == "🏠 Dashboard":
    st.markdown('<div class="section-header">Dashboard Overview</div>', unsafe_allow_html=True)
    df = pd.DataFrame(tickets) if tickets else pd.DataFrame(
        columns=["id","title","platform","priority","status","progress","created_at","due_date","description","requestor","tags"])

    c1,c2,c3,c4,c5 = st.columns(5)
    for col,label,value,color in [
        (c1,"Total Tickets",len(df),"#3b82f6"),
        (c2,"In Progress",  len(df[df.status=="In Progress"]) if len(df) else 0,"#3b82f6"),
        (c3,"In Review",    len(df[df.status=="In Review"])   if len(df) else 0,"#a855f7"),
        (c4,"Blocked",      len(df[df.status=="Blocked"])     if len(df) else 0,"#ef4444"),
        (c5,"Done",         len(df[df.status=="Done"])        if len(df) else 0,"#22c55e"),
    ]:
        with col:
            st.markdown(f'<div class="metric-card"><h1 style="color:{color}">{value}</h1><p>{label}</p></div>',
                        unsafe_allow_html=True)

    if not df.empty:
        st.markdown("---")
        r1,r2 = st.columns(2), st.columns(2)

        with r1[0]:
            sc = df["status"].value_counts().reset_index(); sc.columns=["status","count"]
            fig=px.pie(sc,names="status",values="count",hole=0.6,title="By Status",
                       color="status",color_discrete_map=STATUS_COLORS)
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
                              font_color="#e2e8f0",title_font_color="#f1f5f9")
            st.plotly_chart(fig,use_container_width=True)

        with r1[1]:
            pc=df["platform"].value_counts().reset_index(); pc.columns=["platform","count"]
            fig2=px.bar(pc,x="platform",y="count",title="By Platform",color="platform",
                        color_discrete_map=PLATFORM_COLORS,text="count")
            fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
                               font_color="#e2e8f0",showlegend=False,title_font_color="#f1f5f9",
                               xaxis=dict(gridcolor="#1e293b"),yaxis=dict(gridcolor="#1e293b"))
            fig2.update_traces(textposition="outside",marker_line_width=0)
            st.plotly_chart(fig2,use_container_width=True)

        with r2[0]:
            pric=df["priority"].value_counts().reindex(PRIORITY_ORDER,fill_value=0).reset_index()
            pric.columns=["priority","count"]
            fig3=px.bar(pric,x="priority",y="count",title="By Priority",color="priority",
                        color_discrete_map=PRIORITY_COLORS,text="count")
            fig3.update_layout(paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
                               font_color="#e2e8f0",showlegend=False,title_font_color="#f1f5f9",
                               xaxis=dict(gridcolor="#1e293b"),yaxis=dict(gridcolor="#1e293b"))
            fig3.update_traces(textposition="outside",marker_line_width=0)
            st.plotly_chart(fig3,use_container_width=True)

        with r2[1]:
            ap=df.groupby("status")["progress"].mean().reset_index(); ap.columns=["status","avg_progress"]
            fig4=px.bar(ap,x="status",y="avg_progress",title="Avg Progress % by Status",
                        color="status",color_discrete_map=STATUS_COLORS,
                        text=ap["avg_progress"].round(1).astype(str)+"%")
            fig4.update_layout(paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
                               font_color="#e2e8f0",showlegend=False,title_font_color="#f1f5f9",
                               xaxis=dict(gridcolor="#1e293b"),yaxis=dict(gridcolor="#1e293b",range=[0,110]))
            fig4.update_traces(textposition="outside",marker_line_width=0)
            st.plotly_chart(fig4,use_container_width=True)

        st.markdown('<div class="section-header">Recent Tickets</div>', unsafe_allow_html=True)
        for t in sorted(tickets,key=lambda x:x.get("created_at",""),reverse=True)[:5]:
            bar_color=STATUS_COLORS.get(t["status"],"#3b82f6")
            st.markdown(f"""<div class="ticket-card">
              <div class="ticket-id">{t['id']}</div>
              <div class="ticket-title">{t['title']}</div>
              <div class="pills">
                {badge(t['platform'],PLATFORM_COLORS.get(t['platform'],'#64748b'),'#1a1a2e')}
                {badge(t['status'],STATUS_COLORS.get(t['status'],'#64748b'))}
                {badge(t['priority'],PRIORITY_COLORS.get(t['priority'],'#64748b'))}
              </div>
              {progress_bar_html(t.get('progress',0),bar_color)}
            </div>""", unsafe_allow_html=True)
    else:
        st.info("No tickets yet — submit your first request!")

# ══════════════════════════════════════════════════════════════════════════════
# SUBMIT REQUEST
# ══════════════════════════════════════════════════════════════════════════════
elif page == "➕ Submit Request":
    st.markdown('<div class="section-header">Submit New Request</div>', unsafe_allow_html=True)
    with st.form("submit_form", clear_on_submit=True):
        c1,c2=st.columns(2)
        with c1:
            title    =st.text_input("Ticket Title *",placeholder="e.g. Sales Dashboard – KPI refresh")
            platform =st.selectbox("Platform *",["Splunk","Power BI"])
            priority =st.selectbox("Priority *",PRIORITY_ORDER)
        with c2:
            requestor=st.text_input("Requestor Name *",placeholder="Your name")
            due_date =st.date_input("Target Due Date",value=date.today())
            tags     =st.text_input("Tags (comma-separated)",placeholder="e.g. kpi, finance, Q2")
        description=st.text_area("Description / Requirements *",
            placeholder="Describe the dashboard or report request in detail…",height=150)
        submitted=st.form_submit_button("🚀 Submit Ticket")

    if submitted:
        if not title or not requestor or not description:
            st.error("Please fill in all required fields (*).")
        else:
            ticket_id="QA-"+str(uuid.uuid4())[:6].upper()
            new_ticket={
                "id":ticket_id,"title":title,"platform":platform,
                "priority":priority,"status":"Backlog","progress":0,
                "requestor":requestor,"due_date":str(due_date),
                "tags":[t.strip() for t in tags.split(",") if t.strip()],
                "description":description,
                "created_at":datetime.now().isoformat(),
                "updated_at":datetime.now().isoformat(),
                "comments":[],
            }
            with st.spinner("Saving to GitHub…"):
                save_and_sync(st.session_state.tickets+[new_ticket])
            st.success(f"✅ Ticket **{ticket_id}** saved to GitHub!")
            st.markdown(f"""<div class="ticket-card">
              <div class="ticket-id">{ticket_id}</div>
              <div class="ticket-title">{title}</div>
              <div class="pills">
                {badge(platform,PLATFORM_COLORS.get(platform,'#64748b'),'#1a1a2e')}
                {badge('Backlog',STATUS_COLORS['Backlog'])}
                {badge(priority,PRIORITY_COLORS.get(priority,'#64748b'))}
              </div>
            </div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# ALL TICKETS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📋 All Tickets":
    st.markdown('<div class="section-header">All Tickets</div>', unsafe_allow_html=True)
    if not tickets:
        st.info("No tickets yet. Submit your first request!")
    else:
        fc1,fc2,fc3,fc4=st.columns(4)
        with fc1: f_platform=st.multiselect("Platform",["Splunk","Power BI"],default=["Splunk","Power BI"])
        with fc2: f_status  =st.multiselect("Status",STATUS_ORDER,default=STATUS_ORDER)
        with fc3: f_priority=st.multiselect("Priority",PRIORITY_ORDER,default=PRIORITY_ORDER)
        with fc4: f_search  =st.text_input("Search",placeholder="title / requestor…")

        filtered=[t for t in tickets
                  if t["platform"] in f_platform
                  and t["status"] in f_status
                  and t["priority"] in f_priority
                  and (not f_search
                       or f_search.lower() in t["title"].lower()
                       or f_search.lower() in t.get("requestor","").lower())]

        sc1,sc2=st.columns([2,1])
        with sc1:
            sort_by=st.selectbox("Sort by",["Created (newest)","Created (oldest)",
                                            "Priority (high→low)","Progress (high→low)","Due Date"])
        with sc2:
            view_mode=st.radio("View",["Cards","Table"],horizontal=True)

        def sort_key(t):
            if sort_by=="Created (newest)":    return t.get("created_at","")
            if sort_by=="Created (oldest)":    return t.get("created_at","")
            if sort_by=="Priority (high→low)": return PRIORITY_ORDER.index(t["priority"])
            if sort_by=="Progress (high→low)": return -t.get("progress",0)
            return t.get("due_date","")

        reverse=sort_by in ["Created (newest)","Progress (high→low)"]
        filtered=sorted(filtered,key=sort_key,reverse=reverse)
        st.caption(f"Showing {len(filtered)} of {len(tickets)} tickets")

        if view_mode=="Cards":
            for t in filtered:
                bar_color=STATUS_COLORS.get(t["status"],"#3b82f6")
                tag_html=" ".join(
                    f'<span style="background:#1e3a5f;color:#93c5fd;padding:1px 8px;border-radius:12px;font-size:11px">{tag}</span>'
                    for tag in t.get("tags",[]))
                st.markdown(f"""<div class="ticket-card">
                  <div class="ticket-id">{t['id']} · {t.get('requestor','')} · Due {t.get('due_date','—')}</div>
                  <div class="ticket-title">{t['title']}</div>
                  <div class="pills">
                    {badge(t['platform'],PLATFORM_COLORS.get(t['platform'],'#64748b'),'#1a1a2e')}
                    {badge(t['status'],STATUS_COLORS.get(t['status'],'#64748b'))}
                    {badge(t['priority'],PRIORITY_COLORS.get(t['priority'],'#64748b'))}
                    {tag_html}
                  </div>
                  {progress_bar_html(t.get('progress',0),bar_color)}
                  <p style="color:#64748b;font-size:13px;margin-top:8px">
                    {t.get('description','')[:180]}{'…' if len(t.get('description',''))>180 else ''}
                  </p>
                </div>""", unsafe_allow_html=True)
        else:
            rows=[{"ID":t["id"],"Title":t["title"],"Platform":t["platform"],"Status":t["status"],
                   "Priority":t["priority"],"Progress %":t.get("progress",0),
                   "Requestor":t.get("requestor",""),"Due Date":t.get("due_date",""),
                   "Created":t.get("created_at","")[:10]} for t in filtered]
            st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

# ══════════════════════════════════════════════════════════════════════════════
# UPDATE TICKET
# ══════════════════════════════════════════════════════════════════════════════
elif page == "✏️ Update Ticket":
    st.markdown('<div class="section-header">Update Ticket</div>', unsafe_allow_html=True)
    if not tickets:
        st.info("No tickets to update yet.")
    else:
        ticket_options={f"{t['id']} – {t['title']}":i for i,t in enumerate(tickets)}
        selected_label=st.selectbox("Select Ticket",list(ticket_options.keys()))
        idx=ticket_options[selected_label]
        t=st.session_state.tickets[idx]

        st.markdown(f"""<div class="ticket-card">
          <div class="ticket-id">{t['id']} · Created {t.get('created_at','')[:10]}</div>
          <div class="ticket-title">{t['title']}</div>
          <div class="pills">
            {badge(t['platform'],PLATFORM_COLORS.get(t['platform'],'#64748b'),'#1a1a2e')}
            {badge(t['status'],STATUS_COLORS.get(t['status'],'#64748b'))}
            {badge(t['priority'],PRIORITY_COLORS.get(t['priority'],'#64748b'))}
          </div>
          <p style="color:#94a3b8;margin-top:8px;font-size:14px">{t.get('description','')}</p>
        </div>""", unsafe_allow_html=True)

        st.markdown("#### Update Fields")
        uc1,uc2,uc3=st.columns(3)
        with uc1: new_status  =st.selectbox("Status",STATUS_ORDER,index=STATUS_ORDER.index(t["status"]))
        with uc2: new_priority=st.selectbox("Priority",PRIORITY_ORDER,index=PRIORITY_ORDER.index(t["priority"]))
        with uc3: new_progress=st.slider("Progress %",0,100,t.get("progress",0),step=5)
        new_comment=st.text_area("Add Comment / Note",placeholder="Describe what was done or blocked…")

        if st.button("💾 Save & Sync to GitHub"):
            updated=list(st.session_state.tickets)
            updated[idx]["status"]    =new_status
            updated[idx]["priority"]  =new_priority
            updated[idx]["progress"]  =new_progress
            updated[idx]["updated_at"]=datetime.now().isoformat()
            if new_comment.strip():
                updated[idx].setdefault("comments",[]).append({
                    "text":new_comment.strip(),
                    "timestamp":datetime.now().isoformat(),
                })
            with st.spinner("Syncing to GitHub…"):
                save_and_sync(updated)
            st.success("✅ Updated and saved to GitHub!")
            st.rerun()

        comments=t.get("comments",[])
        if comments:
            st.markdown("#### 💬 Comment History")
            for c in reversed(comments):
                st.markdown(f"""<div style="background:#1e293b;border-radius:10px;padding:12px 16px;margin-bottom:8px">
                  <p style="color:#94a3b8;font-size:11px;margin:0 0 4px">{c['timestamp'][:16].replace('T',' ')}</p>
                  <p style="color:#e2e8f0;margin:0;font-size:14px">{c['text']}</p>
                </div>""", unsafe_allow_html=True)

        st.markdown("---")
        with st.expander("🗑️ Danger Zone"):
            st.warning("This will permanently delete the ticket from GitHub.")
            if st.button("Delete This Ticket",type="secondary"):
                updated=[t for i,t in enumerate(st.session_state.tickets) if i!=idx]
                with st.spinner("Deleting…"):
                    save_and_sync(updated)
                st.success("Ticket deleted.")
                st.rerun()
