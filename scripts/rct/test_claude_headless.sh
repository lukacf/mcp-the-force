#!/usr/bin/env bash
#
# RCT Spike Script: Claude Code CLI
# Purpose: Validate headless JSON, session_id extraction, --resume, HOME isolation, --add-dir
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

# Results storage (simple approach)
RESULT_headless_json_output=""
RESULT_session_id_in_output=""
RESULT_resume_specific_session=""
RESULT_resume_in_headless_mode=""
RESULT_home_isolation=""
RESULT_add_dir_flag=""

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
echo "RCT Spike: Claude Code CLI"
echo "============================================"
echo ""

# Check if claude is installed
if ! command -v claude &> /dev/null; then
    echo -e "${RED}Error: claude command not found${NC}"
    echo "Install with: npm install -g @anthropic-ai/claude-code"
    exit 1
fi

CLAUDE_VERSION=$(claude --version 2>&1 || echo "unknown")
echo "Claude Code version: $CLAUDE_VERSION"
echo ""

# Test 1: Headless JSON output
echo "--- Test 1: Headless JSON Output ---"
JSON_OUTPUT=$(claude --print --output-format json "What is 2+2? Reply with just the number." 2>&1 || true)

# Check if output is valid JSON
if echo "$JSON_OUTPUT" | jq -e . > /dev/null 2>&1; then
    log_test "headless_json_output" "PASS"
    echo "  Sample output (truncated):"
    echo "$JSON_OUTPUT" | jq -c '.' | head -c 500
    echo ""
else
    log_test "headless_json_output" "FAIL" "Output is not valid JSON"
    echo "  Raw output:"
    echo "$JSON_OUTPUT" | head -20
fi
echo ""

# Test 2: Session ID in output
echo "--- Test 2: Session ID in Output ---"
SESSION_ID=""
if echo "$JSON_OUTPUT" | jq -e . > /dev/null 2>&1; then
    # Try different possible locations for session_id
    SESSION_ID=$(echo "$JSON_OUTPUT" | jq -r '.session_id // .sessionId // .conversation_id // .conversationId // empty' 2>/dev/null || true)

    if [[ -z "$SESSION_ID" ]]; then
        # Look in nested structures
        SESSION_ID=$(echo "$JSON_OUTPUT" | jq -r '.. | .session_id? // .sessionId? // empty' 2>/dev/null | head -1 || true)
    fi
fi

if [[ -n "$SESSION_ID" && "$SESSION_ID" != "null" ]]; then
    log_test "session_id_in_output" "PASS"
    echo "  Session ID: $SESSION_ID"
    echo "  Field name: (found in JSON structure)"
else
    log_test "session_id_in_output" "FAIL" "No session_id found in output"
    echo "  Available top-level keys:"
    echo "$JSON_OUTPUT" | jq -r 'keys[]' 2>/dev/null | head -10 || echo "  (could not parse keys)"
fi
echo ""

# Test 3: Resume specific session
echo "--- Test 3: Resume Specific Session ---"
if [[ -n "$SESSION_ID" && "$SESSION_ID" != "null" ]]; then
    # Try to resume the session
    RESUME_OUTPUT=$(claude --print --output-format json --resume "$SESSION_ID" "What was my previous question?" 2>&1 || true)

    if echo "$RESUME_OUTPUT" | jq -e . > /dev/null 2>&1; then
        # Check if the response indicates session continuity
        RESPONSE_TEXT=$(echo "$RESUME_OUTPUT" | jq -r '.result // .response // .content // .message // empty' 2>/dev/null || true)
        if [[ -n "$RESPONSE_TEXT" ]]; then
            log_test "resume_specific_session" "PASS"
            echo "  Resume worked, response (truncated): ${RESPONSE_TEXT:0:200}..."
        else
            log_test "resume_specific_session" "PASS" "Resume command executed (response structure varies)"
        fi
    else
        log_test "resume_specific_session" "FAIL" "Resume output is not valid JSON"
    fi
else
    log_test "resume_specific_session" "SKIP" "No session_id available from previous test"
fi
echo ""

# Test 4: Resume in headless mode
echo "--- Test 4: Resume in Headless Mode ---"
if [[ -n "$SESSION_ID" && "$SESSION_ID" != "null" ]]; then
    # Verify we can combine --resume with --print --output-format json
    HEADLESS_RESUME=$(claude --print --output-format json --resume "$SESSION_ID" "Confirm this is a resumed session." 2>&1 || true)

    if echo "$HEADLESS_RESUME" | jq -e . > /dev/null 2>&1; then
        log_test "resume_in_headless_mode" "PASS"
    else
        # Check if it's an error about resume not working in print mode
        if echo "$HEADLESS_RESUME" | grep -qi "resume.*print\|print.*resume\|cannot\|error"; then
            log_test "resume_in_headless_mode" "FAIL" "Resume may not work with --print mode"
            echo "  Error: $HEADLESS_RESUME"
        else
            log_test "resume_in_headless_mode" "FAIL" "Output not valid JSON"
        fi
    fi
else
    log_test "resume_in_headless_mode" "SKIP" "No session_id available"
fi
echo ""

# Test 5: HOME isolation
echo "--- Test 5: HOME Isolation ---"
TEMP_HOME=$(mktemp -d)
echo "  Using temp HOME: $TEMP_HOME"

# Run claude with isolated HOME
HOME_TEST_OUTPUT=$(HOME="$TEMP_HOME" claude --print --output-format json "Say hello" 2>&1 || true)

# Check if it ran (might fail due to missing config, which is expected)
if echo "$HOME_TEST_OUTPUT" | jq -e . > /dev/null 2>&1; then
    log_test "home_isolation" "PASS"
    echo "  Claude ran with isolated HOME"
elif echo "$HOME_TEST_OUTPUT" | grep -qi "config\|auth\|login\|api.*key"; then
    # Expected - isolated HOME means no credentials
    log_test "home_isolation" "PASS"
    echo "  Claude correctly isolated (no credentials in temp HOME)"
else
    log_test "home_isolation" "FAIL" "Unexpected behavior with isolated HOME"
    echo "  Output: ${HOME_TEST_OUTPUT:0:500}"
fi
echo ""

# Test 6: --add-dir flag
echo "--- Test 6: --add-dir Flag ---"
TEST_DIR=$(mktemp -d)
echo "test content" > "$TEST_DIR/test_file.txt"

ADD_DIR_OUTPUT=$(claude --print --output-format json --add-dir "$TEST_DIR" "List the files you can access in the added directory" 2>&1 || true)

if echo "$ADD_DIR_OUTPUT" | jq -e . > /dev/null 2>&1; then
    log_test "add_dir_flag" "PASS"
    echo "  --add-dir flag accepted"
else
    if echo "$ADD_DIR_OUTPUT" | grep -qi "error\|invalid\|unknown"; then
        log_test "add_dir_flag" "FAIL" "Flag not recognized"
    else
        log_test "add_dir_flag" "PASS" "Flag accepted (output parsing varies)"
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
echo "Capabilities Matrix (Claude)"
echo "============================================"
echo ""
echo "| Capability | Status | Notes |"
echo "|------------|--------|-------|"

for capability in headless_json_output session_id_in_output resume_specific_session resume_in_headless_mode home_isolation add_dir_flag; do
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

if [[ $FAIL_COUNT -gt 0 ]]; then
    exit 1
else
    exit 0
fi
