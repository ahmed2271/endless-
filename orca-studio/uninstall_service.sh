#!/usr/bin/env bash
# Remove the ORCA Studio service. Your profiles, libraries, database and calculations are kept.
set -euo pipefail
systemctl --user disable --now orca-studio 2>/dev/null || true
rm -f "$HOME/.config/systemd/user/orca-studio.service"
systemctl --user daemon-reload
echo "Service removed. Data in ~/dft_projects/.studio and your calculation folders is untouched."
