#!/usr/bin/env bash
# Upload a local file to the slot that the Fish Audio MCP's create_media_upload
# (or get_upload_url) tool returned.
#
#   bash scripts/upload.sh me/photo.jpg "<upload_url>" image/jpeg
#
# Pass the same content type you gave create_media_upload (get_upload_url slots
# take any, so pass "" for those). Prints the HTTP status: 200 means it landed.
set -euo pipefail
file="$1"; url="$2"; type="${3:-}"
if [ -n "$type" ]; then
  curl -sS -o /dev/null -w "%{http_code}\n" -X PUT -H "Content-Type: $type" --data-binary @"$file" "$url"
else
  curl -sS -o /dev/null -w "%{http_code}\n" -X PUT --data-binary @"$file" "$url"
fi
