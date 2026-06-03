#!/usr/bin/env python3

"""
Minimaler Jira Teil Restore.

Dieses Skript liest ein einzelnes Issue JSON aus dem Backup
und erstellt daraus ein neues Jira Issue.
"""

import base64
import json
import os
import sys
from pathlib import Path
from typing import Dict

import requests


JIRA_BASE_URL = os.environ["JIRA_BASE_URL"].rstrip("/")
JIRA_EMAIL = os.environ["JIRA_EMAIL"]
JIRA_API_TOKEN = os.environ["JIRA_API_TOKEN"]
TARGET_PROJECT_KEY = os.environ.get("TARGET_PROJECT_KEY", "")
TARGET_ISSUE_TYPE = os.environ.get("TARGET_ISSUE_TYPE", "Task")


def auth_header() -> Dict[str, str]:
    """Erstellt den Jira Auth Header."""
    raw_token = f"{JIRA_EMAIL}:{JIRA_API_TOKEN}".encode("utf-8")
    encoded_token = base64.b64encode(raw_token).decode("ascii")

    return {
        "Authorization": f"Basic {encoded_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def main() -> None:
    """Erstellt ein neues Jira Issue aus einer Backup Datei."""
    if len(sys.argv) < 2:
        print("Bitte Issue JSON Datei angeben.")
        sys.exit(1)

    if not TARGET_PROJECT_KEY:
        print("TARGET_PROJECT_KEY fehlt.")
        sys.exit(1)

    issue_file = Path(sys.argv[1])

    with issue_file.open("r", encoding="utf-8") as handle:
        backup_issue = json.load(handle)

    fields = backup_issue.get("fields", {})

    payload = {
        "fields": {
            "project": {
                "key": TARGET_PROJECT_KEY,
            },
            "summary": fields.get("summary", "Wiederhergestelltes Jira Issue"),
            "description": fields.get("description"),
            "issuetype": {
                "name": TARGET_ISSUE_TYPE,
            },
        }
    }

    response = requests.post(
        f"{JIRA_BASE_URL}/rest/api/3/issue",
        headers=auth_header(),
        json=payload,
        timeout=60,
    )

    response.raise_for_status()
    created_issue = response.json()

    print(f"Neues Issue erstellt: {created_issue['key']}")


if __name__ == "__main__":
    main()
