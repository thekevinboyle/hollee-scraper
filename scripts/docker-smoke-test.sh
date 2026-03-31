#!/bin/bash
# Docker Compose smoke test for Oil & Gas Document Scraper.
# Run from project root with Docker Compose running.
set -euo pipefail

PASS=0
FAIL=0
TOTAL=0

pass() { echo "  ✓ $1"; PASS=$((PASS + 1)); TOTAL=$((TOTAL + 1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL + 1)); TOTAL=$((TOTAL + 1)); }

echo "=== Oil & Gas Document Scraper — Docker Smoke Test ==="
echo ""

# --- Test 1: All containers running ---
echo "[1/8] Check all containers are running"
for svc in db backend worker frontend; do
    if docker compose ps --status running | grep -q "$svc"; then
        pass "$svc is running"
    else
        fail "$svc is NOT running"
    fi
done
echo ""

# --- Test 2: Database health ---
echo "[2/8] Database health"
if docker compose exec -T db pg_isready -U ogdocs -d ogdocs >/dev/null 2>&1; then
    pass "PostgreSQL is ready"
else
    fail "PostgreSQL is NOT ready"
fi

# PostGIS extension
if docker compose exec -T db psql -U ogdocs -d ogdocs -c "SELECT PostGIS_Version();" >/dev/null 2>&1; then
    pass "PostGIS extension is installed"
else
    fail "PostGIS extension is NOT installed"
fi
echo ""

# --- Test 3: Backend health ---
echo "[3/8] Backend API health"
HEALTH=$(curl -sf http://localhost:8000/health 2>/dev/null || echo "FAIL")
if echo "$HEALTH" | grep -q "ok\|healthy"; then
    pass "Backend /health responds"
else
    fail "Backend /health failed: $HEALTH"
fi
echo ""

# --- Test 4: Frontend health ---
echo "[4/8] Frontend health"
HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" http://localhost:3000 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    pass "Frontend responds with 200"
else
    fail "Frontend returned $HTTP_CODE"
fi
echo ""

# --- Test 5: API endpoints respond ---
echo "[5/8] API endpoint checks"
ENDPOINTS=(
    "GET /api/v1/states"
    "GET /api/v1/wells/?page=1&page_size=1"
    "GET /api/v1/documents/?page=1&page_size=1"
    "GET /api/v1/stats/"
    "GET /api/v1/review/?page=1&page_size=1"
    "GET /api/v1/scrape/jobs?page=1&page_size=1"
)
for ep in "${ENDPOINTS[@]}"; do
    METHOD=$(echo "$ep" | awk '{print $1}')
    PATH=$(echo "$ep" | awk '{print $2}')
    CODE=$(curl -sf -o /dev/null -w "%{http_code}" -X "$METHOD" "http://localhost:8000${PATH}" 2>/dev/null || echo "000")
    if [ "$CODE" = "200" ]; then
        pass "$METHOD $PATH → $CODE"
    else
        fail "$METHOD $PATH → $CODE"
    fi
done
echo ""

# --- Test 6: States seeded ---
echo "[6/8] Database seed data"
STATES_COUNT=$(curl -sf http://localhost:8000/api/v1/states/ 2>/dev/null | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
if [ "$STATES_COUNT" = "10" ]; then
    pass "10 states seeded in database"
else
    fail "Expected 10 states, found $STATES_COUNT"
fi
echo ""

# --- Test 7: API response times ---
echo "[7/8] API response time benchmarks (<500ms)"
BENCHMARK_ENDPOINTS=(
    "/health"
    "/api/v1/states/"
    "/api/v1/wells/?page=1&page_size=10"
    "/api/v1/stats/"
)
for path in "${BENCHMARK_ENDPOINTS[@]}"; do
    TIME_MS=$(curl -sf -o /dev/null -w "%{time_total}" "http://localhost:8000${path}" 2>/dev/null || echo "999")
    TIME_MS_INT=$(echo "$TIME_MS * 1000" | bc 2>/dev/null | cut -d. -f1 || echo "999")
    if [ "$TIME_MS_INT" -lt 500 ]; then
        pass "$path → ${TIME_MS_INT}ms"
    else
        fail "$path → ${TIME_MS_INT}ms (>500ms)"
    fi
done
echo ""

# --- Test 8: No error logs ---
echo "[8/8] Check for backend error logs (last 50 lines)"
ERROR_COUNT=$(docker compose logs --tail=50 backend 2>/dev/null | grep -ci "error\|traceback\|exception" || echo "0")
if [ "$ERROR_COUNT" -lt 3 ]; then
    pass "No significant errors in backend logs ($ERROR_COUNT minor)"
else
    fail "$ERROR_COUNT error-related lines in backend logs"
fi
echo ""

# --- Summary ---
echo "=== Results ==="
echo "  Passed: $PASS / $TOTAL"
echo "  Failed: $FAIL / $TOTAL"
echo ""

if [ "$FAIL" -gt 0 ]; then
    echo "SMOKE TEST FAILED"
    exit 1
else
    echo "SMOKE TEST PASSED"
    exit 0
fi
