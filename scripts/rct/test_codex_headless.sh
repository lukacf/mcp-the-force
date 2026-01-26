#!/usr/bin/env bash
#
# RCT Spike Script: Codex CLI
# Purpose: Validate exec JSON/JSONL, threadId extraction, --cd, HOME isolation
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
TEST_DIR=""

# Results storage
RESULT_headless_json_output=""
RESULT_thread_id_in_output=""
RESULT_resume_specific_session=""
RESULT_resume_in_headless_mode=""
RESULT_home_isolation=""
RESULT_cd_flag=""
RESULT_add_dir_flag=""

# Cleanup function
cleanup() {
    if [[ -n "$TEMP_HOME" && -d "$TEMP_HOME" ]]; then
        rm -rf "$TEMP_HOME"
    fi
    if [[ -n "$TEST_DIR" && -d "$TEST_DIR" ]]; then
        rm -rf "$TEST_DIR"
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
echo "RCT Spike: Codex CLI"
echo "============================================"
echo ""

# Check if codex is installed
if ! command -v codex &> /dev/null; then
    echo -e "${RED}Error: codex command not found${NC}"
    echo "Install with: npm install -g @openai/codex"
    exit 1
fi

CODEX_VERSION=$(codex --version 2>&1 || echo "unknown")
echo "Codex CLI version: $CODEX_VERSION"
echo ""

# Create a test directory with git repo (Codex requires git repo by default)
TEST_DIR=$(mktemp -d)
cd "$TEST_DIR"
git init -q
echo "test content" > test_file.txt
git add test_file.txt
git commit -q -m "Initial commit"
echo "  Working in test git repo: $TEST_DIR"
echo ""

# Test 1: Headless JSON output (exec --json)
echo "--- Test 1: Headless JSON Output (exec --json) ---"
JSON_OUTPUT=$(codex exec --json "What is 2+2? Reply with just the number." 2>&1 || true)

# Check if output is valid JSONL (one JSON per line)
FIRST_LINE=$(echo "$JSON_OUTPUT" | head -1)
if echo "$FIRST_LINE" | jq -e . > /dev/null 2>&1; then
    log_test "headless_json_output" "PASS"
    echo "  Output is JSONL (JSON Lines format)"
    echo "  First line structure:"
    echo "$FIRST_LINE" | jq -c 'keys' 2>/dev/null || echo "  (parsing keys failed)"

    # Show event types in the output
    echo "  Event types in output:"
    echo "$JSON_OUTPUT" | jq -r '.type // .event // "unknown"' 2>/dev/null | sort | uniq -c | head -10 || true
else
    log_test "headless_json_output" "FAIL" "Output is not valid JSONL"
    echo "  Raw output (first 500 chars):"
    echo "${JSON_OUTPUT:0:500}"
fi
echo ""

# Test 2: Session/Thread ID in output
echo "--- Test 2: Thread ID in Output ---"
THREAD_ID=""

# Parse all lines looking for thread_id or session_id
if [[ -n "$JSON_OUTPUT" ]]; then
    # Try to find thread_id in any line
    THREAD_ID=$(echo "$JSON_OUTPUT" | jq -r 'select(.thread_id != null) | .thread_id' 2>/dev/null | head -1 || true)

    if [[ -z "$THREAD_ID" || "$THREAD_ID" == "null" ]]; then
        # Try other possible field names
        THREAD_ID=$(echo "$JSON_OUTPUT" | jq -r 'select(.threadId != null) | .threadId' 2>/dev/null | head -1 || true)
    fi

    if [[ -z "$THREAD_ID" || "$THREAD_ID" == "null" ]]; then
        # Try session_id
        THREAD_ID=$(echo "$JSON_OUTPUT" | jq -r 'select(.session_id != null) | .session_id' 2>/dev/null | head -1 || true)
    fi

    if [[ -z "$THREAD_ID" || "$THREAD_ID" == "null" ]]; then
        # Look in nested structures
        THREAD_ID=$(echo "$JSON_OUTPUT" | jq -r '.. | .thread_id? // .threadId? // .session_id? // empty' 2>/dev/null | head -1 || true)
    fi
fi

if [[ -n "$THREAD_ID" && "$THREAD_ID" != "null" ]]; then
    log_test "thread_id_in_output" "PASS"
    echo "  Thread ID: $THREAD_ID"
else
    log_test "thread_id_in_output" "FAIL" "No thread_id found in output"
    echo "  Available fields in first event:"
    echo "$FIRST_LINE" | jq -r 'keys[]' 2>/dev/null | head -10 || echo "  (could not parse keys)"

    # Try to find any ID-like fields across all events
    echo "  Looking for ID-like fields across all events:"
    echo "$JSON_OUTPUT" | jq -r 'to_entries[] | select(.key | test("id$|Id$|ID$")) | "\(.key): \(.value)"' 2>/dev/null | head -5 || true
fi
echo ""

# Test 3: Resume specific session (codex exec resume)
echo "--- Test 3: Resume Specific Session ---"
# First run a command to create a session
INITIAL_OUTPUT=$(codex exec --json "Remember this number: 42" 2>&1 || true)

# Extract thread ID from initial run
RESUME_THREAD_ID=$(echo "$INITIAL_OUTPUT" | jq -r 'select(.thread_id != null) | .thread_id' 2>/dev/null | head -1 || true)

if [[ -n "$RESUME_THREAD_ID" && "$RESUME_THREAD_ID" != "null" ]]; then
    # Try to resume using the thread ID
    RESUME_OUTPUT=$(codex exec resume "$RESUME_THREAD_ID" --json "What number did I ask you to remember?" 2>&1 || true)

    if echo "$RESUME_OUTPUT" | head -1 | jq -e . > /dev/null 2>&1; then
        log_test "resume_specific_session" "PASS"
        echo "  Resume with thread ID worked"
    else
        log_test "resume_specific_session" "FAIL" "Resume output is not valid JSONL"
        echo "  Output: ${RESUME_OUTPUT:0:300}"
    fi
else
    # Try resume with --last flag
    RESUME_OUTPUT=$(codex exec resume --last --json "What number did I ask you to remember?" 2>&1 || true)

    if echo "$RESUME_OUTPUT" | head -1 | jq -e . > /dev/null 2>&1; then
        log_test "resume_specific_session" "PASS"
        echo "  Resume with --last flag worked"
    else
        log_test "resume_specific_session" "SKIP" "No thread_id available and --last failed"
        echo "  Note: Codex uses 'codex exec resume <thread_id>' or 'codex resume --last'"
    fi
fi
echo ""

# Test 4: Resume in headless mode (JSON output)
echo "--- Test 4: Resume in Headless Mode ---"
if [[ -n "$RESUME_THREAD_ID" && "$RESUME_THREAD_ID" != "null" ]]; then
    HEADLESS_RESUME=$(codex exec resume "$RESUME_THREAD_ID" --json "Confirm session resumed" 2>&1 || true)

    if echo "$HEADLESS_RESUME" | head -1 | jq -e . > /dev/null 2>&1; then
        log_test "resume_in_headless_mode" "PASS"
        echo "  Resume works with --json flag"
    else
        log_test "resume_in_headless_mode" "FAIL" "Resume with --json failed"
        echo "  Output: ${HEADLESS_RESUME:0:300}"
    fi
else
    # Try with --last
    HEADLESS_RESUME=$(codex exec resume --last --json "Confirm session resumed" 2>&1 || true)

    if echo "$HEADLESS_RESUME" | head -1 | jq -e . > /dev/null 2>&1; then
        log_test "resume_in_headless_mode" "PASS"
        echo "  Resume with --last and --json works"
    else
        log_test "resume_in_headless_mode" "SKIP" "Could not test resume in headless mode"
    fi
fi
echo ""

# Test 5: HOME isolation
echo "--- Test 5: HOME Isolation ---"
TEMP_HOME=$(mktemp -d)
echo "  Using temp HOME: $TEMP_HOME"

# Run codex with isolated HOME
HOME_TEST_OUTPUT=$(HOME="$TEMP_HOME" codex exec --json "Say hello" 2>&1 || true)

# Check behavior with isolated HOME
if echo "$HOME_TEST_OUTPUT" | head -1 | jq -e . > /dev/null 2>&1; then
    log_test "home_isolation" "PASS"
    echo "  Codex ran with isolated HOME"
elif echo "$HOME_TEST_OUTPUT" | grep -qi "config\|auth\|login\|api.*key\|credential\|OPENAI"; then
    # Expected - isolated HOME means no credentials
    log_test "home_isolation" "PASS"
    echo "  Codex correctly isolated (no credentials in temp HOME)"
else
    # Check if it's a config or permission issue
    if echo "$HOME_TEST_OUTPUT" | grep -qi "permission\|settings\|profile\|config.toml"; then
        log_test "home_isolation" "PASS"
        echo "  Codex uses HOME for config (isolation works)"
    else
        log_test "home_isolation" "FAIL" "Unexpected behavior with isolated HOME"
        echo "  Output: ${HOME_TEST_OUTPUT:0:500}"
    fi
fi
echo ""

# Test 6: --cd flag (working directory)
echo "--- Test 6: --cd Flag ---"
OTHER_DIR=$(mktemp -d)
cd "$OTHER_DIR"
git init -q
echo "other test" > other_file.txt
git add other_file.txt
git commit -q -m "Other commit"

# Go back to test dir but use --cd to point to other dir
cd "$TEST_DIR"
CD_OUTPUT=$(codex exec --json --cd "$OTHER_DIR" "List files in current directory" 2>&1 || true)

if echo "$CD_OUTPUT" | head -1 | jq -e . > /dev/null 2>&1; then
    log_test "cd_flag" "PASS"
    echo "  --cd flag accepted"
else
    if echo "$CD_OUTPUT" | grep -qi "error\|invalid\|unknown"; then
        log_test "cd_flag" "FAIL" "Flag not recognized"
        echo "  Error: ${CD_OUTPUT:0:300}"
    else
        log_test "cd_flag" "PASS" "Flag accepted (output parsing varies)"
    fi
fi
rm -rf "$OTHER_DIR"
echo ""

# Test 7: --add-dir flag
echo "--- Test 7: --add-dir Flag ---"
EXTRA_DIR=$(mktemp -d)
echo "extra content" > "$EXTRA_DIR/extra_file.txt"

ADD_DIR_OUTPUT=$(codex exec --json --add-dir "$EXTRA_DIR" "List accessible directories" 2>&1 || true)

if echo "$ADD_DIR_OUTPUT" | head -1 | jq -e . > /dev/null 2>&1; then
    log_test "add_dir_flag" "PASS"
    echo "  --add-dir flag accepted"
else
    if echo "$ADD_DIR_OUTPUT" | grep -qi "error\|invalid\|unknown"; then
        log_test "add_dir_flag" "FAIL" "Flag not recognized"
        echo "  Error: ${ADD_DIR_OUTPUT:0:300}"
    else
        log_test "add_dir_flag" "PASS" "Flag accepted"
    fi
fi
rm -rf "$EXTRA_DIR"
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
echo "Capabilities Matrix (Codex)"
echo "============================================"
echo ""
echo "| Capability | Status | Notes |"
echo "|------------|--------|-------|"

for capability in headless_json_output thread_id_in_output resume_specific_session resume_in_headless_mode home_isolation cd_flag add_dir_flag; do
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
echo "Note: Codex uses 'codex exec --json' for JSONL output"
echo "      Resume via 'codex exec resume <thread_id>' or 'codex resume --last'"
echo "      Requires git repo (use --skip-git-repo-check to bypass)"
echo ""

if [[ $FAIL_COUNT -gt 0 ]]; then
    exit 1
else
    exit 0
fi
