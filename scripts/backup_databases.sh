#!/bin/bash
# Backup SQLite databases to prevent data loss
#
# OS Compatibility: macOS, Linux
# Note: This script uses bash-specific features and may not work on Windows without WSL

# Get backup directory from config, with fallback
BACKUP_DIR_FROM_CONFIG=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && python -c "
try:
    from mcp_the_force.config import get_settings
    print(get_settings().backup.path)
except:
    pass
" 2>/dev/null)
BACKUP_DIR="${BACKUP_DIR_FROM_CONFIG:-.mcp-the-force/backups}"
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

# Backup all SQLite databases
cd "$PROJECT_DIR"
for db in .mcp-the-force/sessions.sqlite3 .mcp-the-force/logs.sqlite3; do
    backup_file "$db"
done

echo "Backup complete. Backups stored in: $BACKUP_DIR"