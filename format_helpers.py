"""
Format helpers for timestamps and data display.
"""

from datetime import datetime
from config import TZ_GMT8


def fmt_ts(ts: str) -> str:
    """Convert ISO timestamp to dd/mm/yy hh:mm AM/PM format."""
    if not ts:
        return "—"
    try:
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(str(ts)[:25], fmt)
                return dt.strftime("%d/%m/%y %I:%M %p")
            except:
                continue
        return str(ts)[:16].replace("T", " ")
    except:
        return str(ts)[:16]


def fmt_due_date(due_date_str: str) -> str:
    """
    Convert due date to YYYY-MM-DD format (date only, no time).
    
    Args:
        due_date_str: Due date string in any format (e.g., "2026-09-14 10:00:00")
    
    Returns:
        Formatted date string as "YYYY-MM-DD" or "—" if invalid
    """
    if not due_date_str:
        return "—"
    
    try:
        # Try to parse various common formats
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(str(due_date_str)[:19], fmt)
                return dt.strftime("%Y-%m-%d")
            except:
                continue
        # Fallback: extract first 10 characters (YYYY-MM-DD)
        return str(due_date_str)[:10]
    except:
        return str(due_date_str)[:10]


def fmt_date_display(date_str: str) -> str:
    """
    Format date for display in tables (DD/MM/YYYY).
    
    Args:
        date_str: Date string
    
    Returns:
        Formatted date string as "DD/MM/YYYY" or "—" if invalid
    """
    if not date_str:
        return "—"
    
    try:
        dt = datetime.strptime(str(date_str)[:10], "%Y-%m-%d")
        return dt.strftime("%d/%m/%Y")
    except:
        return str(date_str)[:10]
