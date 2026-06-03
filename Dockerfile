# Nutzt ein kleines Python Basisimage.
FROM python:3.12-slim

# Installiert Werkzeuge für tar, gzip, jq und curl.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       tar \
       gzip \
       ca-certificates \
       jq \
       curl \
    && rm -rf /var/lib/apt/lists/*

# Setzt den Arbeitsordner im Container.
WORKDIR /app

# Kopiert zuerst die Python Abhängigkeiten.
COPY requirements.txt /app/requirements.txt

# Installiert Python Pakete.
RUN pip install --no-cache-dir -r /app/requirements.txt

# Kopiert alle Skripte in den Container.
COPY jira_api_backup.py /app/jira_api_backup.py
COPY run-backup.sh /app/run-backup.sh
COPY restore_issue_minimal.py /app/restore_issue_minimal.py
COPY restore_comments.py /app/restore_comments.py
COPY README.md /app/README.md

# Macht das Backup Skript ausführbar.
RUN chmod +x /app/run-backup.sh

# Erstellt Datenordner.
RUN mkdir -p /data/backups /data/archives /data/restore-test

# Hält den Container aktiv.
CMD ["sleep", "infinity"]
