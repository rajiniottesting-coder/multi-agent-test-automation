#!/usr/bin/env bash
# Install the test browser and the operating-system packages it needs.
#
# 11 Nov 2026: for about fifteen minutes runners could not resolve the package
# mirrors ("Temporary failure resolving 'archive.ubuntu.com'"). The install
# failed, the framework self-test after it was skipped, and the runs were red -
# yet every browser test then ran and passed: the runner image already carries
# the libraries the browser needs, and only optional font packages were missing.
#
# So: the full install (browser + OS packages) is tried twice. If the package
# mirrors stay unreachable, the browser alone is installed and STARTED once; the
# step passes, with a warning, only when the browser really launches. A browser
# that cannot start still fails the step, saying why.
# Usage: scripts/install_browser.sh [browser]   (default: chromium)
set -u
browser="${1:-chromium}"
for attempt in 1 2; do
  if playwright install --with-deps "$browser"; then
    exit 0
  fi
  if [ "$attempt" -lt 2 ]; then
    echo "::warning::Installing $browser with its OS packages failed (attempt $attempt of 2) - trying again in 30s"
    sleep 30
  fi
done
echo "::warning::The OS packages for $browser could not be installed (package mirrors unreachable) - installing the browser alone and checking that it starts"
if playwright install "$browser" && python - "$browser" <<'PY'
import sys
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    getattr(p, sys.argv[1]).launch(headless=True).close()
PY
then
  echo "::warning::$browser starts without the freshly installed OS packages - the run continues"
  exit 0
fi
echo "::error::$browser could not be installed with its OS packages, and does not start without them"
exit 1
