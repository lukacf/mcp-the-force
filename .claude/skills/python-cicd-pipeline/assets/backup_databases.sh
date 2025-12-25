#!/bin/bash
# Backup SQLite databases to prevent data loss
# Add to pre-commit hooks if your project uses SQLite databases
#
# Usage: Place in scripts/ directory and add to .pre-commit-config.yaml:
#   - repo: local
#     hooks:
#       - id: backup-databases
#         name: Backup SQLite databases
#         entry: scripts/backup_databases.sh
#         language: system
#         pass_filenames: false
#         always_run: true

BACKUP_DIR="${BACKUP_DIR:-.backups}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Function to backup a file with timestamp
backup_file() {
    local file="$1"
    local basename=$(basename "$file")
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_name="${basename%.sqlite3}_${timestamp}.sqlite3"

    if [ -f "$file" ]; then
        cp "$file" "$BACKUP_DIR/$backup_name"
        echo "Backed up $basename to $BACKUP_DIR/$backup_name"

        # Keep only the 10 most recent backups for each file
        ls -t "$BACKUP_DIR/${basename%.sqlite3}_"*.sqlite3 2>/dev/null | tail -n +11 | xargs -r rm
    fi
}

# Find and backup all SQLite databases
cd "$PROJECT_DIR"
for db in $(find . -maxdepth 3 -name "*.sqlite3" -type f 2>/dev/null); do
    backup_file "$db"
done

echo "Backup complete. Backups stored in: $BACKUP_DIR"
