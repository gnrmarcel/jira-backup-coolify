#!/usr/bin/env python3

"""
Stellt Kommentare aus einem Jira API Backup an einem Ziel Issue wieder her.
"""

import base64
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import requests


JIRA_BASE_URL = os.environ["JIRA_BASE_URL"].rstrip("/")
JIRA_EMAIL = os.environ["JIRA_EMAIL"]
JIRA_API_TOKEN = os.environ["JIRA_API_TOKEN"]


def auth_header() -> Dict[str, str]:
    """Erstellt den Jira Auth Header."""
    raw_token = f"{JIRA_EMAIL}:{JIRA_API_TOKEN}".encode("utf-8")
    encoded_token = base64.b64encode(raw_token).decode("ascii")

    return {
        "Authorization": f"Basic {encoded_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def extract_comments(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Liest Kommentare aus typischen Jira Antwortstrukturen."""
    if "comments" in data:
        return data["comments"]

    if "values" in data:
        return data["values"]

    return []


def make_comment_payload(original_comment: Dict[str, Any]) -> Dict[str, Any]:
    """Erstellt einen Jira Kommentar mit Restore Hinweis."""
    author = original_comment.get("author", {}).get("displayName", "Unbekannt")
    created = original_comment.get("created", "Unbekannt")
    body = original_comment.get("body", "")

    restored_text = json.dumps(body, ensure_ascii=False) if isinstance(body, dict) else str(body)

    text = (
        f"Wiederhergestellter Kommentar aus Backup.\n"
        f"Ursprünglicher Autor: {author}\n"
        f"Ursprüngliches Datum: {created}\n\n"
        f"{restored_text}"
    )

    return {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": text,
                        }
                    ],
                }
            ],
        }
    }


def main() -> None:
    """Hängt Backup Kommentare an ein Ziel Issue."""
    if len(sys.argv) < 3:
        print("Nutzung:")
        print("python3 restore_comments.py comments/ABC-1.json ABC-123")
        sys.exit(1)

    comment_file = Path(sys.argv[1])
    target_issue_key = sys.argv[2]

    with comment_file.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    comments = extract_comments(data)

    for comment in comments:
        response = requests.post(
            f"{JIRA_BASE_URL}/rest/api/3/issue/{target_issue_key}/comment",
            headers=auth_header(),
            json=make_comment_payload(comment),
            timeout=60,
        )

        response.raise_for_status()
        print(f"Kommentar an {target_issue_key} wiederhergestellt.")


if __name__ == "__main__":
    main()
