#!/usr/bin/env bash
# Re-run EVERY verification step from a clean checkout. Takes ~3-4 minutes. Exits non-zero on the first failure.
#   scripts/verify_all.sh
# Needs: python3 (3.11+), node 20+, curl. First run installs dependencies into backend/.venv and frontend/node_modules.
# Real Meta check is separate (needs your credential):  backend/scripts/check_meta_live.py <photo.jpg>
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
step() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

step "1/9 backend: install"
[ -d backend/.venv ] || python3 -m venv backend/.venv
backend/.venv/bin/pip install -q -r backend/requirements-dev.txt
export PYTHON="$ROOT/backend/.venv/bin/python"

step "2/9 backend: full test-suite (incl. real-HTTP tests against the local stub provider, OpenAPI + contract-doc checks)"
(cd backend && "$PYTHON" -m pytest tests -q -W ignore -p no:cacheprovider)

step "3/9 backend: API contract document is current"
(cd backend && "$PYTHON" -W ignore scripts/generate_api_contract.py --check) && echo "docs/API_CONTRACT.md is up to date"

step "4/9 frontend: install, typecheck, lint, unit+contract tests, production build"
(cd frontend && { [ -d node_modules ] || npm install --no-audit --no-fund --legacy-peer-deps; } && npx tsc --noEmit -p . && echo "tsc clean" \
  && npx eslint src --max-warnings=9999 | tail -3 && npx vitest run 2>&1 | grep -E "Test Files|Tests " && npx vite build 2>&1 | grep -E "built in" | tail -1)

step "5/9 secrets: no credentials in the production bundle or frontend source"
if grep -rIlE "stub-key|sk-[A-Za-z0-9]{12,}|Bearer [A-Za-z0-9]{8,}" frontend/.output 2>/dev/null; then echo "FAIL: credential-like string in build output"; exit 1; fi
if grep -rn "META_API_KEY\|META_MODEL" frontend/src --include=*.ts --include=*.tsx | grep -v "src/test/"; then echo "FAIL: frontend source references credentials"; exit 1; fi
echo "no credential-like strings in frontend/.output or frontend/src"

step "6/9 live API test against a RUNNING backend with NO vision provider configured"
scripts/stack.sh stop >/dev/null 2>&1 || true
scripts/stack.sh start none
(cd frontend && VITE_APP_MODE=backend VITE_API_BASE_URL=http://127.0.0.1:8000 LIVE_API=1 npx vitest run src/test/live-backend.test.ts 2>&1 | grep -E "Test Files|Tests ")
scripts/stack.sh stop

step "7/9 live API test against a RUNNING backend wired to the LOCAL STUB provider (not Meta)"
scripts/stack.sh start stub
(cd frontend && VITE_APP_MODE=backend VITE_API_BASE_URL=http://127.0.0.1:8000 LIVE_API=1 EXPECT_STUB=1 npx vitest run src/test/live-backend.test.ts 2>&1 | grep -E "Test Files|Tests ")

step "8/9 browser end-to-end (real Chromium, real UI, real backend; demo mode checked separately)"
(cd frontend/e2e && { [ -d node_modules ] || npm install --no-audit --no-fund; } && node e2e.mjs)

step "9/9 stop stack"
scripts/stack.sh stop
printf '\n\033[1mALL CHECKS PASSED\033[0m\n(The stub is not Meta. Run backend/scripts/check_meta_live.py with a real key to verify the live Meta integration.)\n'
