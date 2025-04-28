#!/bin/bash
set -e

echo "--- Installing Git ---"
# Install git quietly
apt-get update > /dev/null && apt-get install -y -qq --no-install-recommends git > /dev/null

# Define variables
REPO_URL="https://github.com/gilo2754/qr_esp32.git"
TARGET_DIR="/app/qr_esp32"

echo "--- Target directory set to: ${TARGET_DIR} ---"
echo "--- Repository URL set to: ${REPO_URL} ---"

# Check if repo directory exists and contains .git folder
if [ ! -d "${TARGET_DIR}/.git" ]; then
  echo "--- Cloning repository ${REPO_URL} into ${TARGET_DIR} ---"
  # Clone if it doesn't exist
  git clone "${REPO_URL}" "${TARGET_DIR}"
else
  echo "--- Repository exists, updating ${TARGET_DIR} ---"
  # If it exists, navigate into it and pull changes
  cd "${TARGET_DIR}"
  git pull origin main
fi

# Ensure we are in the correct directory before starting server
cd "${TARGET_DIR}"
echo "--- Starting HTTP server in $(pwd) ---"
python -m http.server 8000 