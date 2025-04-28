#!/bin/bash
set -e

echo '--- Ensuring git is installed ---'
# Install git silently
apt-get update > /dev/null && apt-get install -y git > /dev/null

REPO_URL='https://github.com/gilo2754/qr_esp32.git'
TARGET_DIR='/data'
# Use always the 'master' branch
BRANCH_NAME="master"
echo "--- Target Git Branch: [$BRANCH_NAME] ---"

# Check if the repository already exists
if [ -d "$TARGET_DIR/.git" ]; then
  echo "--- Repository exists in $TARGET_DIR. Updating branch '$BRANCH_NAME'... ---"
  cd "$TARGET_DIR"
  # Bring remote changes
  git fetch origin
  # Change to the desired branch
  git checkout "$BRANCH_NAME"
  # Ensure local branch matches remote exactly
  git reset --hard "origin/$BRANCH_NAME"
  # Clean untracked files
  git clean -fdx
  # Pull
  git pull origin "$BRANCH_NAME"
else
  echo "--- Repository does not exist in $TARGET_DIR. Cloning branch '$BRANCH_NAME'... ---"
  # Clone only the specific branch into the target directory
  git clone --single-branch --branch "$BRANCH_NAME" "$REPO_URL" "$TARGET_DIR"
fi

# Go to the correct subdirectory and start the server
APP_DIR="$TARGET_DIR/qr_esp32"
if [ -d "$APP_DIR" ]; then
  echo "--- Starting HTTP server in $APP_DIR directory ---"
  cd "$APP_DIR"
  # Use exec to replace the shell process with the python server
  exec python3 -m http.server 80
else
  echo "ERROR: Directory '$APP_DIR' not found after git operations!"
  exit 1
fi 