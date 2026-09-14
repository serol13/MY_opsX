"""
Data models and GitHub operations for ticket management.
"""

import pandas as pd
import requests
import base64
import io
import streamlit as st
from typing import Tuple, Optional, Dict, Any
from datetime import datetime
from config import (
    get_github_config,
    FILE_PATHS,
    TICKET_COLUMNS,
    RECURRING_COLUMNS,
    ACTIVITY_COLUMNS,
    TZ_GMT8,
)


class GitHubDataManager:
    """Manages all GitHub API operations for CSV files."""

    def __init__(self):
        """Initialize GitHub manager with config."""
        self.config = get_github_config()
        self.token = self.config["token"]
        self.repo = self.config["repo"]
        self.branch = self.config["branch"]
        self.headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }

    def _build_api_url(self, file_key: str) -> str:
        """Build GitHub API URL for a file."""
        file_path = FILE_PATHS.get(file_key, "")
        return f"https://api.github.com/repos/{self.repo}/contents/{file_path}"

    def load_csv(self, file_key: str, columns: list) -> Tuple[pd.DataFrame, Optional[str]]:
        """
        Load CSV file from GitHub.

        Args:
            file_key: Key for the file (tickets, recurring, activity)
            columns: List of expected columns

        Returns:
            Tuple of (DataFrame, SHA hash) or (empty DataFrame, None) if not found
        """
        try:
            url = self._build_api_url(file_key)
            response = requests.get(url, headers=self.headers)

            if response.status_code == 404:
                return pd.DataFrame(columns=columns), None

            response.raise_for_status()
            data = response.json()
            content = base64.b64decode(data["content"]).decode("utf-8")
            df = pd.read_csv(io.StringIO(content), dtype=str).fillna("")

            # Ensure all expected columns exist
            for col in columns:
                if col not in df.columns:
                    df[col] = ""

            return df[columns], data.get("sha")

        except Exception as e:
            st.error(f"Error loading {file_key}: {e}")
            return pd.DataFrame(columns=columns), None

    def save_csv(
        self,
        file_key: str,
        df: pd.DataFrame,
        sha: Optional[str] = None,
        message: str = "Update data",
    ) -> bool:
        """
        Save CSV file to GitHub.

        Args:
            file_key: Key for the file
            df: DataFrame to save
            sha: Current file SHA (required for updates)
            message: Commit message

        Returns:
            True if successful, False otherwise
        """
        try:
            csv_content = df.to_csv(index=False).encode("utf-8")
            encoded_content = base64.b64encode(csv_content).decode("utf-8")

            payload = {
                "message": message,
                "content": encoded_content,
                "branch": self.branch,
            }

            if sha:
                payload["sha"] = sha

            url = self._build_api_url(file_key)
            response = requests.put(url, headers=self.headers, json=payload)
            response.raise_for_status()

            return True

        except Exception as e:
            st.error(f"Error saving {file_key}: {e}")
            return False


class TicketManager:
    """Manages ticket operations."""

    def __init__(self):
        """Initialize ticket manager."""
        self.github = GitHubDataManager()

    def load_tickets(self) -> Tuple[pd.DataFrame, Optional[str]]:
        """Load all tickets from GitHub."""
        return self.github.load_csv("tickets", TICKET_COLUMNS)

    def save_tickets(self, df: pd.DataFrame, sha: Optional[str], message: str) -> bool:
        """Save tickets to GitHub."""
        return self.github.save_csv("tickets", df, sha, message)

    def add_ticket(self, ticket_data: Dict[str, Any]) -> bool:
        """
        Add a new ticket.

        Args:
            ticket_data: Dictionary containing ticket information

        Returns:
            True if successful
        """
        df, sha = self.load_tickets()

        # Create new row with required fields
        new_row = {col: "" for col in TICKET_COLUMNS}
        new_row.update(ticket_data)
        new_row["timestamp"] = self._get_current_timestamp()
        new_row["action"] = "CREATED"

        # Append new ticket
        updated_df = pd.concat(
            [df, pd.DataFrame([new_row])], ignore_index=True
        )

        message = (
            f"[{new_row['action']}] {new_row['ticket_id']} "
            f"📌 {new_row['title']} | "
            f"by {new_row.get('updated_by', 'Unknown')} "
            f"⏰ {new_row['timestamp'][:16]}"
        )

        return self.save_tickets(updated_df, sha, message)

    def update_ticket(self, ticket_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update an existing ticket.

        Args:
            ticket_id: ID of ticket to update
            updates: Dictionary of fields to update

        Returns:
            True if successful
        """
        df, sha = self.load_tickets()

        # Find and update the ticket
        mask = df["ticket_id"] == ticket_id
        if not mask.any():
            st.error(f"Ticket {ticket_id} not found")
            return False

        for col, value in updates.items():
            if col in df.columns:
                df.loc[mask, col] = value

        df.loc[mask, "timestamp"] = self._get_current_timestamp()

        message = (
            f"[UPDATED] {ticket_id} "
            f"📝 {df.loc[mask, 'title'].values[0]} | "
            f"by {updates.get('updated_by', 'Unknown')}"
        )

        return self.save_tickets(df, sha, message)

    def get_current_tickets(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Get only active/current tickets (exclude deleted).

        Args:
            df: Full ticket DataFrame

        Returns:
            Filtered DataFrame with current tickets
        """
        if df.empty:
            return pd.DataFrame(columns=TICKET_COLUMNS)

        # Convert progress to numeric for filtering
        df["progress"] = pd.to_numeric(df["progress"], errors="coerce").fillna(0).astype(int)

        # Get only CREATED and UPDATED actions
        active = df[df["action"].isin(["CREATED", "UPDATED"])].copy()

        if active.empty:
            return pd.DataFrame(columns=TICKET_COLUMNS)

        # Get latest action for each ticket
        latest = active.sort_values("timestamp").groupby(
            "ticket_id", as_index=False
        ).last()

        # Exclude deleted tickets
        deleted = set(df[df["action"] == "DELETED"]["ticket_id"].tolist())
        result = latest[~latest["ticket_id"].isin(deleted)].reset_index(drop=True)

        return result

    @staticmethod
    def _get_current_timestamp() -> str:
        """Get current timestamp in GMT+8."""
        return datetime.now(TZ_GMT8).isoformat()


class RecurringTaskManager:
    """Manages recurring tasks."""

    def __init__(self):
        """Initialize recurring task manager."""
        self.github = GitHubDataManager()

    def load_tasks(self) -> Tuple[pd.DataFrame, Optional[str]]:
        """Load all recurring tasks."""
        return self.github.load_csv("recurring", RECURRING_COLUMNS)

    def save_tasks(self, df: pd.DataFrame, sha: Optional[str]) -> bool:
        """Save recurring tasks."""
        return self.github.save_csv("recurring", df, sha, "Update recurring tasks")

    def add_task(self, task_data: Dict[str, Any]) -> bool:
        """Add a new recurring task."""
        df, sha = self.load_tasks()

        new_row = {col: "" for col in RECURRING_COLUMNS}
        new_row.update(task_data)
        new_row["created_at"] = self._get_current_timestamp()

        updated_df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        return self.save_tasks(updated_df, sha)

    def get_active_tasks(self, df: pd.DataFrame) -> pd.DataFrame:
        """Get only active recurring tasks."""
        if df.empty:
            return df
        return df[df["active"].astype(str).str.lower() == "true"].reset_index(drop=True)

    @staticmethod
    def _get_current_timestamp() -> str:
        """Get current timestamp in GMT+8."""
        return datetime.now(TZ_GMT8).isoformat()


class ActivityLogger:
    """Manages activity log."""

    def __init__(self):
        """Initialize activity logger."""
        self.github = GitHubDataManager()

    def load_log(self) -> Tuple[pd.DataFrame, Optional[str]]:
        """Load activity log."""
        return self.github.load_csv("activity", ACTIVITY_COLUMNS)

    def save_log(self, df: pd.DataFrame, sha: Optional[str]) -> bool:
        """Save activity log."""
        return self.github.save_csv("activity", df, sha, "Update activity log")

    def log_activity(self, activity_data: Dict[str, Any]) -> bool:
        """
        Log a new activity.

        Args:
            activity_data: Dictionary with activity details

        Returns:
            True if successful
        """
        df, sha = self.load_log()

        now = datetime.now(TZ_GMT8)
        new_row = {col: "" for col in ACTIVITY_COLUMNS}
        new_row.update(activity_data)
        new_row["timestamp"] = now.isoformat()
        new_row["date"] = now.strftime("%Y-%m-%d")

        updated_df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

        message = (
            f"[ACTIVITY] {activity_data.get('username', 'Unknown')} "
            f"⏰ {new_row['date']}"
        )

        return self.save_log(updated_df, sha)
