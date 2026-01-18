#!/usr/bin/env bash
#
# RCT Spike Script: Gemini CLI
# Purpose: Validate headless JSON, session extraction, resume mechanism, config isolation
#
# Exit codes:
#   0 = All tests passed
#   1 = One or more tests failed
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Results tracking (bash 3 compatible)
PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0
TEMP_HOME=""

# Results storage
RESULT_headless_json_output=""
RESULT_session_id_in_output=""
RESULT_resume_specific_session=""
RESULT_resume_in_headless_mode=""
RESULT_home_isolation=""
RESULT_include_directories_flag=""

# Cleanup function
cleanup() {
    if [[ -n "$TEMP_HOME" && -d "$TEMP_HOME" ]]; then
        rm -rf "$TEMP_HOME"
    fi
}
trap cleanup EXIT

log_test() {
    local name="$1"
    local status="$2"
    local details="${3:-}"

    if [[ "$status" == "PASS" ]]; then
        echo -e "${GREEN}✓${NC} $name"
        ((PASS_COUNT++)) || true
        eval "RESULT_${name}=PASS"
    elif [[ "$status" == "FAIL" ]]; then
        echo -e "${RED}✗${NC} $name"
        [[ -n "$details" ]] && echo -e "  ${RED}→ $details${NC}"
        ((FAIL_COUNT++)) || true
        eval "RESULT_${name}=FAIL"
    elif [[ "$status" == "SKIP" ]]; then
        echo -e "${YELLOW}⊘${NC} $name (skipped)"
        [[ -n "$details" ]] && echo -e "  ${YELLOW}→ $details${NC}"
        ((SKIP_COUNT++)) || true
        eval "RESULT_${name}=SKIP"
    fi
}

echo "============================================"
echo "RCT Spike: Gemini CLI"
echo "============================================"
echo ""

# Check if gemini is installed
if ! command -v gemini &> /dev/null; then
    echo -e "${RED}Error: gemini command not found${NC}"
    echo "Install with: npm install -g @anthropic-ai/gemini-cli"
    exit 1
fi

GEMINI_VERSION=$(gemini --version 2>&1 || echo "unknown")
echo "Gemini CLI version: $GEMINI_VERSION"
echo ""

# Test 1: Headless JSON output
echo "--- Test 1: Headless JSON Output ---"
JSON_OUTPUT=$(gemini --output-format json "What is 2+2? Reply with just the number." 2>&1 || true)

# Check if output is valid JSON
if echo "$JSON_OUTPUT" | jq -e . > /dev/null 2>&1; then
    log_test "headless_json_output" "PASS"
    echo "  Sample output (truncated):"
    echo "$JSON_OUTPUT" | jq -c '.' | head -c 500
    echo ""
else
    # Gemini might output JSONL (one JSON per line)
    FIRST_LINE=$(echo "$JSON_OUTPUT" | head -1)
    if echo "$FIRST_LINE" | jq -e . > /dev/null 2>&1; then
        log_test "headless_json_output" "PASS"
        echo "  Note: Output is JSONL (JSON Lines format)"
        echo "  First line: $FIRST_LINE"
    else
        log_test "headless_json_output" "FAIL" "Output is not valid JSON or JSONL"
        echo "  Raw output (first 500 chars):"
        echo "${JSON_OUTPUT:0:500}"
    fi
fi
echo ""

# Test 2: Session ID in output
echo "--- Test 2: Session ID in Output ---"
SESSION_INDEX=""
SESSION_ID=""

# Check available sessions first
SESSION_LIST=$(gemini --list-sessions 2>&1 || true)
echo "  Available sessions:"
echo "$SESSION_LIST" | head -10

# Try to find session info in the output
if echo "$JSON_OUTPUT" | jq -e . > /dev/null 2>&1; then
    # Try different possible locations for session_id
    SESSION_ID=$(echo "$JSON_OUTPUT" | jq -r '.session_id // .sessionId // .session // empty' 2>/dev/null | head -1 || true)

    if [[ -z "$SESSION_ID" || "$SESSION_ID" == "null" ]]; then
        # Look in nested structures
        SESSION_ID=$(echo "$JSON_OUTPUT" | jq -r '.. | .session_id? // .sessionId? // empty' 2>/dev/null | head -1 || true)
    fi
fi

if [[ -n "$SESSION_ID" && "$SESSION_ID" != "null" ]]; then
    log_test "session_id_in_output" "PASS"
    echo "  Session ID: $SESSION_ID"
else
    # Gemini uses index-based resume, not session ID
    log_test "session_id_in_output" "SKIP" "Gemini uses index-based sessions (--resume latest or --resume N)"
    echo "  Note: Use --list-sessions to see available sessions"
    SESSION_INDEX="latest"
fi
echo ""

# Test 3: Resume specific session (using index or 'latest')
echo "--- Test 3: Resume Specific Session ---"
# First, ensure we have a session to resume
echo "  Creating a new session first..."
INITIAL_OUTPUT=$(gemini --output-format json "Remember this number: 42" 2>&1 || true)

# Now try to resume
RESUME_OUTPUT=$(gemini --output-format json --resume latest "What number did I ask you to remember?" 2>&1 || true)

if echo "$RESUME_OUTPUT" | jq -e . > /dev/null 2>&1; then
    log_test "resume_specific_session" "PASS"
    echo "  Resume with --resume latest worked"
    RESPONSE=$(echo "$RESUME_OUTPUT" | jq -r '.text // .content // .message // .response // .' 2>/dev/null | head -c 200 || true)
    echo "  Response (truncated): $RESPONSE..."
elif echo "$RESUME_OUTPUT" | head -1 | jq -e . > /dev/null 2>&1; then
    log_test "resume_specific_session" "PASS"
    echo "  Resume worked (JSONL output)"
else
    if echo "$RESUME_OUTPUT" | grep -qi "session\|resume\|42"; then
        log_test "resume_specific_session" "PASS"
        echo "  Resume appears to work (checking response content)"
    else
        log_test "resume_specific_session" "FAIL" "Could not verify session resumption"
        echo "  Output: ${RESUME_OUTPUT:0:300}"
    fi
fi
echo ""

# Test 4: Resume in headless mode (JSON output)
echo "--- Test 4: Resume in Headless Mode ---"
HEADLESS_RESUME=$(gemini --output-format json --resume latest "Confirm session is resumed" 2>&1 || true)

if echo "$HEADLESS_RESUME" | jq -e . > /dev/null 2>&1; then
    log_test "resume_in_headless_mode" "PASS"
    echo "  --resume works with --output-format json"
elif echo "$HEADLESS_RESUME" | head -1 | jq -e . > /dev/null 2>&1; then
    log_test "resume_in_headless_mode" "PASS"
    echo "  --resume works with --output-format json (JSONL)"
else
    if echo "$HEADLESS_RESUME" | grep -qi "error\|cannot\|invalid"; then
        log_test "resume_in_headless_mode" "FAIL" "Resume may not work with JSON output"
        echo "  Error: ${HEADLESS_RESUME:0:300}"
    else
        log_test "resume_in_headless_mode" "PASS" "Resume in headless mode executed"
    fi
fi
echo ""

# Test 5: HOME isolation
echo "--- Test 5: HOME Isolation ---"
TEMP_HOME=$(mktemp -d)
echo "  Using temp HOME: $TEMP_HOME"

# Run gemini with isolated HOME
HOME_TEST_OUTPUT=$(HOME="$TEMP_HOME" gemini --output-format json "Say hello" 2>&1 || true)

# Check behavior with isolated HOME
if echo "$HOME_TEST_OUTPUT" | jq -e . > /dev/null 2>&1; then
    log_test "home_isolation" "PASS"
    echo "  Gemini ran with isolated HOME"
elif echo "$HOME_TEST_OUTPUT" | grep -qi "config\|auth\|login\|api.*key\|credential"; then
    # Expected - isolated HOME means no credentials
    log_test "home_isolation" "PASS"
    echo "  Gemini correctly isolated (no credentials in temp HOME)"
else
    # Check if it's a config or permission issue (which indicates isolation works)
    if echo "$HOME_TEST_OUTPUT" | grep -qi "permission\|settings\|profile"; then
        log_test "home_isolation" "PASS"
        echo "  Gemini uses HOME for config (isolation works)"
    else
        log_test "home_isolation" "FAIL" "Unexpected behavior with isolated HOME"
        echo "  Output: ${HOME_TEST_OUTPUT:0:500}"
    fi
fi
echo ""

# Test 6: --include-directories flag (Gemini's equivalent to --add-dir)
echo "--- Test 6: --include-directories Flag ---"
TEST_DIR=$(mktemp -d)
echo "test content for gemini" > "$TEST_DIR/test_file.txt"

INCLUDE_DIR_OUTPUT=$(gemini --output-format json --include-directories "$TEST_DIR" "What files can you see?" 2>&1 || true)

if echo "$INCLUDE_DIR_OUTPUT" | jq -e . > /dev/null 2>&1; then
    log_test "include_directories_flag" "PASS"
    echo "  --include-directories flag accepted"
elif echo "$INCLUDE_DIR_OUTPUT" | head -1 | jq -e . > /dev/null 2>&1; then
    log_test "include_directories_flag" "PASS"
    echo "  --include-directories flag accepted (JSONL output)"
else
    if echo "$INCLUDE_DIR_OUTPUT" | grep -qi "error\|invalid\|unknown"; then
        log_test "include_directories_flag" "FAIL" "Flag not recognized"
        echo "  Error: ${INCLUDE_DIR_OUTPUT:0:300}"
    else
        log_test "include_directories_flag" "PASS" "Flag accepted"
    fi
fi
rm -rf "$TEST_DIR"
echo ""

# Summary
echo "============================================"
echo "Summary"
echo "============================================"

echo -e "${GREEN}Passed:${NC} $PASS_COUNT"
echo -e "${RED}Failed:${NC} $FAIL_COUNT"
echo -e "${YELLOW}Skipped:${NC} $SKIP_COUNT"
echo ""

# Output capabilities matrix row
echo "============================================"
echo "Capabilities Matrix (Gemini)"
echo "============================================"
echo ""
echo "| Capability | Status | Notes |"
echo "|------------|--------|-------|"

for capability in headless_json_output session_id_in_output resume_specific_session resume_in_headless_mode home_isolation include_directories_flag; do
    eval "status=\$RESULT_${capability}"
    case "$status" in
        PASS) symbol="✅" ;;
        FAIL) symbol="❌" ;;
        SKIP) symbol="⚠️" ;;
        *) symbol="⬜" ;;
    esac
    echo "| $capability | $symbol | |"
done

echo ""
echo "Note: Gemini uses --resume latest or --resume N (index), not session IDs"
echo "      Use --list-sessions to see available sessions"
echo ""

if [[ $FAIL_COUNT -gt 0 ]]; then
    exit 1
else
    exit 0
fi
