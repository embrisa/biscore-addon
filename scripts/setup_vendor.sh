#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR_DIR="$ROOT_DIR/vendor"
REPO_DIR="$VENDOR_DIR/wow-classic-items"
TAG="tbc-1.0.0"
REPO_URL="https://github.com/nexus-devs/wow-classic-items"

mkdir -p "$VENDOR_DIR"

if [ ! -d "$REPO_DIR/.git" ]; then
  git clone --depth 1 --branch "$TAG" "$REPO_URL" "$REPO_DIR"
  echo "Cloned $REPO_URL at $TAG into $REPO_DIR"
  exit 0
fi

cd "$REPO_DIR"
git fetch --depth 1 origin "refs/tags/$TAG:refs/tags/$TAG"
git checkout "$TAG"
echo "Updated existing vendor repo to tag $TAG"
