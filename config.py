"""
Application configuration and constants.
"""

import streamlit as st
from datetime import timedelta, timezone
from typing import Dict

# ============================================================================
# TIMEZONE
# ============================================================================
TZ_GMT8 = timezone(timedelta(hours=8))


# ============================================================================
# GITHUB CONFIGURATION
# ============================================================================
def get_github_config() -> Dict[str, str]:
    """Load GitHub configuration from secrets."""
    return {
        "token": st.secrets.get("GITHUB_TOKEN", ""),
        "repo": st.secrets.get("GITHUB_REPO", ""),
        "branch": "main",
    }


# ============================================================================
# FILE PATHS
# ============================================================================
FILE_PATHS = {
    "tickets": "tickets.csv",
    "recurring": "recurring.csv",
    "activity": "activity_log.csv",
}

# ============================================================================
# CSV COLUMN SCHEMAS
# ============================================================================
TICKET_COLUMNS = [
    "timestamp",
    "action",
    "ticket_id",
    "title",
    "platform",
    "priority",
    "status",
    "progress",
    "requestor",
    "due_date",
    "tags",
    "description",
    "updated_by",
    "notes",
    "complexity",
    "assigned_to",
    "image",
    "category",
]

RECURRING_COLUMNS = [
    "task_id",
    "title",
    "description",
    "frequency",
    "day_info",
    "assigned_to",
    "platform",
    "created_by",
    "created_at",
    "active",
]

ACTIVITY_COLUMNS = [
    "timestamp",
    "date",
    "username",
    "category",
    "description",
    "duration_min",
]

# ============================================================================
# RESPONSE TIME CATEGORIES
# ============================================================================
RESPONSE_CATEGORIES = {
    "R1 (Within 24 hours)": timedelta(hours=24),
    "R2 (Within 2 days)": timedelta(days=2),
    "R3 (Within 5 days)": timedelta(days=5),
}

# ============================================================================
# DHL BRANDING - COLOR PALETTE
# ============================================================================
COLORS = {
    "PRIMARY_YELLOW": "#FFCC00",
    "PRIMARY_RED": "#D40511",
    "DARK": "#1A1A1A",
    "GRAY": "#6B6B6B",
    "LIGHT": "#F5F5F5",
    "BORDER": "#E0E0E0",
    "WHITE": "#FFFFFF",
}

# ============================================================================
# PLATFORM COLORS
# ============================================================================
PLATFORM_COLORS = {
    "Splunk": COLORS["PRIMARY_RED"],
    "Power BI": "#0078D4",
    "Others": COLORS["GRAY"],
}

# ============================================================================
# STATUS CONFIGURATION
# ============================================================================
STATUS_ORDER = ["Backlog", "In Progress", "In Review", "Blocked", "Done"]

STATUS_COLORS = {
    "Backlog": "#95B8D1",
    "In Progress": "#FFCC00",
    "In Review": "#FF9D56",
    "Blocked": "#D40511",
    "Done": "#55B5A3",
}

# ============================================================================
# PRIORITY CONFIGURATION
# ============================================================================
PRIORITY_ORDER = ["Low", "Medium", "High", "Critical"]

PRIORITY_COLORS = {
    "Low": "#95B8D1",
    "Medium": "#FFCC00",
    "High": "#FF9D56",
    "Critical": "#D40511",
}

# ============================================================================
# COMPLEXITY CONFIGURATION
# ============================================================================
COMPLEXITY_ORDER = ["Simple", "Medium", "Complex", "Critical"]

COMPLEXITY_COLORS = {
    "Simple": "#55B5A3",
    "Medium": "#FFCC00",
    "Complex": "#FF9D56",
    "Critical": "#D40511",
}

# ============================================================================
# CHART CONFIGURATION
# ============================================================================
CHART_CONFIG = {
    "responsive": True,
    "displayModeBar": True,
    "displaylogo": False,
}

# ============================================================================
# PAGE CONFIGURATION
# ============================================================================
PAGE_META = {
    "title": "Operation Excellence Tracker",
    "icon": "📊",
    "layout": "wide",
    "initial_sidebar_state": "expanded",
}

# ============================================================================
# AUTHENTICATION
# ============================================================================
GUEST_PIN = st.secrets.get("GUEST_PIN", "")
USERS: Dict[str, str] = dict(st.secrets.get("users", {}))
