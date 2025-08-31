#!/bin/bash
# This script is a wrapper for the main exporter.py script and is non-essential
#
# It loads the plex username from a config file at ./config.yaml, if it exists.
# This more or less functions as a CLI memory if you, like me, infrequently
# record your watch history on Letterboxd.

# Configuration
USER=""                         # Plex username (auto-detected from config or set manually)
FROM_DATE=""                    # Start date (YYYY-MM-DD) or leave empty for all
CONFIG_FILE="config.yaml"       # Config file to use
OUTPUT_PREFIX="plex-watched"    # Output filename prefix

set -e

# Try to extract user from config file
if [ -f "${CONFIG_FILE}" ] && [ -z "${USER}" ]; then
    CONFIG_USER=$(grep -E "^\s*user:" "${CONFIG_FILE}" | sed 's/.*user:\s*//' | sed 's/\s*#.*//' | xargs)
    if [ -n "${CONFIG_USER}" ] && [ "${CONFIG_USER}" != "null" ]; then
        USER="${CONFIG_USER}"
        echo "Using user from config: ${USER}"
    fi
fi

# Validate user is set
if [ -z "${USER}" ] || [ "${USER}" = "null" ]; then
    echo "✖ Error: No user specified."
    echo "Either:"
    echo "1. Set 'export.user: your_username' in ${CONFIG_FILE}"
    echo "2. Or edit USER variable at top of this script"
    exit 1
fi

echo "Personal Plex → Letterboxd Export Workflow"
echo "========================================="

# Generate filename with current date
DATE=$(date +%Y-%m-%d)
OUTPUT_FILE="${OUTPUT_PREFIX}-${USER}-${DATE}.csv"

echo "Exporting Plex watch history..."
echo "User: ${USER}"
echo "From: ${FROM_DATE:-all history}"
echo "Config: ${CONFIG_FILE}"
echo "Output: ${OUTPUT_FILE}"

# Build command with optional parameters
CMD="python3 exporter.py --config ${CONFIG_FILE} --user ${USER} --output ${OUTPUT_FILE}"
if [ -n "${FROM_DATE}" ]; then
    CMD="${CMD} --from-date ${FROM_DATE}"
fi

# Export from Plex
${CMD}

echo "✔ Export complete: ${OUTPUT_FILE}"

# Show file stats
ENTRY_COUNT=$(tail -n +2 "${OUTPUT_FILE}" | wc -l)
echo "✔ Exported ${ENTRY_COUNT} watch entries"

echo ""
echo "Next steps:"
echo "1. Upload ${OUTPUT_FILE} to https://letterboxd.com/import/"
echo "2. Or compare with existing Letterboxd data:"
echo "   i.  Export Letterboxd history to CSV: https://letterboxd.com/user/exportdata"
echo "   ii. python3 compare.py --plex ${OUTPUT_FILE} --letterboxd path/to/letterboxd-export.csv"
