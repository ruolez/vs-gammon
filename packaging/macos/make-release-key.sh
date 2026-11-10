#!/usr/bin/env bash
# One-time: creates the update signing key in ~/.config/vs-gammon and records its public half in the repo.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$HERE/build"
swiftc -O -o "$HERE/build/release-key" "$HERE/tools/release-key.swift"
"$HERE/build/release-key" keygen > "$HERE/release-public-key.txt"
echo "public key written to $HERE/release-public-key.txt; back up ~/.config/vs-gammon/release.key"
