#!/usr/bin/env python3

"""
Jira Cloud API Backup für Coolify.

Dieses Skript exportiert Jira Cloud Daten über die REST API.
Es speichert Issues, Kommentare, Worklogs, Changelogs, Attachments,
Metadaten und einfache Agile Daten als Dateien unter BACKUP_ROOT.

Das Ergebnis ist ein API Datenbackup und kein vollständiges
Atlassian Systembackup für einen 1:1 Restore.
"""

import base64
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


JIRA_BASE_URL = os.environ["JIRA_BASE_URL"].rstrip("/")
JIRA_EMAIL = os.environ["JIRA_EMAIL"]
JIRA_API_TOKEN = os.environ["JIRA_API_TOKEN"]
JIRA_JQL = os.environ.get("JIRA_JQL", "order by key asc")
BACKUP_ROOT = Path(os.environ.get("BACKUP_ROOT", "/data/backups"))

PAGE_SIZE = 100


def build_auth_header() -> Dict[str, str]:
    """Erstellt den Basic Auth Header für Jira Cloud."""
    raw_token = f"{JIRA_EMAIL}:{JIRA_API_TOKEN}".encode("utf-8")
    encoded_token = base64.b64encode(raw_token).decode("ascii")

    return {
        "Authorization": f"Basic {encoded_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def jira_request(method: str, url: str, **kwargs: Any) -> requests.Response:
    """Führt einen Jira API Request aus und gibt bei Fehlern die Jira Antwort aus."""
    headers = kwargs.pop("headers", {})
    headers.update(build_auth_header())

    for attempt in range(1, 8):
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            timeout=180,
            **kwargs,
        )

        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", "30"))
            sleep_seconds = retry_after + attempt
            print(f"Rate Limit erreicht. Warte {sleep_seconds} Sekunden.", file=sys.stderr)
            time.sleep(sleep_seconds)
            continue

        if response.status_code >= 500:
            sleep_seconds = min(60, attempt * 10)
            print(f"Serverfehler {response.status_code}. Warte {sleep_seconds} Sekunden.", file=sys.stderr)
            time.sleep(sleep_seconds)
            continue

        if response.status_code >= 400:
            print("Jira API Fehler:", file=sys.stderr)
            print(f"URL: {url}", file=sys.stderr)
            print(f"Status: {response.status_code}", file=sys.stderr)
            print("Antwort:", file=sys.stderr)
            print(response.text, file=sys.stderr)
            response.raise_for_status()

        return response

    raise RuntimeError(f"Request mehrfach fehlgeschlagen: {url}")


def safe_filename(value: str) -> str:
    """Bereinigt Dateinamen für das Dateisystem."""
    allowed_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_"
    return "".join(char if char in allowed_chars else "_" for char in value)


def write_json(path: Path, data: Any) -> None:
    """Speichert Daten als lesbare JSON Datei."""
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)


def sha256_file(path: Path) -> str:
    """Berechnet die SHA256 Prüfsumme einer Datei."""
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def create_manifest(backup_dir: Path) -> None:
    """Erstellt eine Manifest Datei für den Backup Lauf."""
    manifest = {
        "backupType": "jira-cloud-api-backup",
        "formatVersion": 1,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "jiraBaseUrl": JIRA_BASE_URL,
        "jql": JIRA_JQL,
    }

    write_json(backup_dir / "manifest.json", manifest)


def export_metadata(backup_dir: Path) -> None:
    """Exportiert wichtige Jira Metadaten."""
    endpoints = {
        "fields": "/rest/api/3/field",
        "issue-types": "/rest/api/3/issuetype",
        "statuses": "/rest/api/3/status",
        "priorities": "/rest/api/3/priority",
        "resolutions": "/rest/api/3/resolution",
        "projects": "/rest/api/3/project/search",
    }

    for name, endpoint in endpoints.items():
        print(f"Exportiere Metadaten: {name}")
        response = jira_request("GET", f"{JIRA_BASE_URL}{endpoint}")
        write_json(backup_dir / "metadata" / f"{name}.json", response.json())


def export_issue_comments(issue_key: str, backup_dir: Path) -> None:
    """Exportiert Kommentare eines Issues."""
    response = jira_request(
        "GET",
        f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/comment",
    )
    write_json(backup_dir / "comments" / f"{safe_filename(issue_key)}.json", response.json())


def export_issue_worklogs(issue_key: str, backup_dir: Path) -> None:
    """Exportiert Worklogs eines Issues."""
    response = jira_request(
        "GET",
        f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/worklog",
    )
    write_json(backup_dir / "worklogs" / f"{safe_filename(issue_key)}.json", response.json())


def export_issue_changelog(issue_key: str, backup_dir: Path) -> None:
    """Exportiert den Changelog eines Issues mit Pagination."""
    start_at = 0
    max_results = 100
    all_values: List[Dict[str, Any]] = []

    while True:
        url = (
            f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/changelog"
            f"?startAt={start_at}&maxResults={max_results}"
        )

        response = jira_request("GET", url)
        data = response.json()

        values = data.get("values", [])
        all_values.extend(values)

        total = data.get("total", len(all_values))
        start_at += len(values)

        if not values or start_at >= total:
            break

    write_json(
        backup_dir / "changelogs" / f"{safe_filename(issue_key)}.json",
        {
            "issueKey": issue_key,
            "values": all_values,
        },
    )


def download_attachment(attachment: Dict[str, Any], issue_key: str, backup_dir: Path) -> Optional[Path]:
    """Lädt ein Attachment herunter."""
    attachment_id = str(attachment.get("id", "unknown"))
    filename = safe_filename(attachment.get("filename", f"attachment-{attachment_id}"))
    content_url = attachment.get("content")

    if not content_url:
        return None

    target_dir = backup_dir / "attachments" / safe_filename(issue_key)
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / f"{attachment_id}-{filename}"

    if target_path.exists():
        return target_path

    response = jira_request(
        "GET",
        content_url,
        headers={
            "Accept": "*/*",
            "Content-Type": "application/octet-stream",
        },
    )

    with target_path.open("wb") as handle:
        handle.write(response.content)

    return target_path


def export_issues(backup_dir: Path) -> None:
    """Exportiert alle Issues anhand der JQL Abfrage."""
    attachment_index: List[Dict[str, Any]] = []
    next_page_token: Optional[str] = None
    page_number = 1

    while True:
        payload: Dict[str, Any] = {
            "jql": JIRA_JQL,
            "maxResults": PAGE_SIZE,
            "fields": ["*all"],
            "expand": "renderedFields,names,schema,transitions,operations,editmeta",
        }

        if next_page_token:
            payload["nextPageToken"] = next_page_token

        response = jira_request(
            "POST",
            f"{JIRA_BASE_URL}/rest/api/3/search/jql",
            json=payload,
        )

        data = response.json()
        issues = data.get("issues", [])

        print(f"Exportiere Issue Seite {page_number} mit {len(issues)} Issues")

        for issue in issues:
            issue_key = issue["key"]
            project_key = issue["fields"]["project"]["key"]

            write_json(
                backup_dir / "issues" / project_key / f"{safe_filename(issue_key)}.json",
                issue,
            )

            export_issue_comments(issue_key, backup_dir)
            export_issue_worklogs(issue_key, backup_dir)
            export_issue_changelog(issue_key, backup_dir)

            attachments = issue.get("fields", {}).get("attachment", [])

            for attachment in attachments:
                downloaded_path = download_attachment(attachment, issue_key, backup_dir)

                if downloaded_path:
                    attachment_index.append(
                        {
                            "issueKey": issue_key,
                            "attachmentId": attachment.get("id"),
                            "filename": attachment.get("filename"),
                            "localPath": str(downloaded_path.relative_to(backup_dir)),
                            "sha256": sha256_file(downloaded_path),
                            "size": downloaded_path.stat().st_size,
                        }
                    )

        next_page_token = data.get("nextPageToken")
        is_last = data.get("isLast", False)

        if is_last or not next_page_token or not issues:
            break

        page_number += 1

    write_json(backup_dir / "attachments" / "attachments-index.json", attachment_index)


def export_agile_data(backup_dir: Path) -> None:
    """Exportiert Boards, Sprints und Board Issues aus Jira Software."""
    boards_response = jira_request("GET", f"{JIRA_BASE_URL}/rest/agile/1.0/board")
    boards_data = boards_response.json()

    write_json(backup_dir / "agile" / "boards.json", boards_data)

    for board in boards_data.get("values", []):
        board_id = board.get("id")

        if not board_id:
            continue

        print(f"Exportiere Agile Daten für Board {board_id}")

        sprints_response = jira_request(
            "GET",
            f"{JIRA_BASE_URL}/rest/agile/1.0/board/{board_id}/sprint",
        )

        write_json(
            backup_dir / "agile" / f"board-{board_id}-sprints.json",
            sprints_response.json(),
        )

        board_issues_response = jira_request(
            "GET",
            f"{JIRA_BASE_URL}/rest/agile/1.0/board/{board_id}/issue",
        )

        write_json(
            backup_dir / "agile" / f"board-{board_id}-issues.json",
            board_issues_response.json(),
        )


def create_checksums(backup_dir: Path) -> None:
    """Erstellt Prüfsummen für alle Backup Dateien."""
    checksum_path = backup_dir / "checksums" / "sha256sums.txt"
    checksum_path.parent.mkdir(parents=True, exist_ok=True)

    with checksum_path.open("w", encoding="utf-8") as handle:
        for path in sorted(backup_dir.rglob("*")):
            if path.is_file() and path != checksum_path:
                relative_path = path.relative_to(backup_dir)
                handle.write(f"{sha256_file(path)}  {relative_path}\n")


def main() -> None:
    """Startet den vollständigen Backup Lauf."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    backup_dir = BACKUP_ROOT / timestamp

    backup_dir.mkdir(parents=True, exist_ok=True)

    print(f"Starte Jira API Backup: {backup_dir}")

    create_manifest(backup_dir)
    export_metadata(backup_dir)
    export_issues(backup_dir)
    export_agile_data(backup_dir)
    create_checksums(backup_dir)

    print(f"Backup abgeschlossen: {backup_dir}")


if __name__ == "__main__":
    main()
