# CLI Agents RCT Findings

> **Phase 0 Completion Report**
> **Date**: 2026-01-17
> **Status**: PROCEED - All critical capabilities validated

---

## Executive Summary

Phase 0 RCT (Representation Contract Tests) validated all three CLI agents (Claude Code, Gemini CLI, Codex CLI) for headless operation, session management, and isolation. **All critical paths work as expected.**

---

## Capabilities Matrix Summary

| Capability | Claude | Gemini | Codex | Notes |
|------------|--------|--------|-------|-------|
| Headless JSON output | ✅ | ✅ | ✅ | Claude: `--print --output-format json`<br>Gemini: `--output-format json`<br>Codex: `exec --json` (JSONL) |
| Session ID in output | ✅ | ✅ | ✅ | Field: `session_id` (Claude/Gemini), `thread_id` (Codex) |
| Resume specific session | ✅ | ✅ | ✅ | Flag: `--resume <id>` (Claude/Gemini), `exec resume <id>` (Codex) |
| Resume in headless mode | ✅ | ✅ | ✅ | All CLIs support combining resume with JSON output |
| HOME isolation works | ✅ | ✅ | ✅ | Custom HOME directory respected by all CLIs |
| Project dir access | ✅ | ✅ | ✅ | Via: `--add-dir` (Claude/Codex), `--include-directories` (Gemini) |

**Legend**: ✅ works, ❌ doesn't work, ⚠️ works with caveats

---

## Detailed Findings by CLI

### Claude Code CLI (v2.1.12)

**Headless JSON Output:**
- Use `claude --print --output-format json "prompt"`
- Output is a single JSON object containing all results
- Structure includes `type`, `session_id`, `tools`, `cwd`, and result content

**Session ID:**
- Field name: `session_id` (in the init event)
- Format: UUID (e.g., `ce68a5fb-ce3f-4360-9473-9b77a7c494de`)
- Available immediately in the first JSON event

**Resume Mechanism:**
- Flag: `--resume <session_id>`
- Works with `--print --output-format json`
- Session history is preserved

**HOME Isolation:**
- Setting `HOME=/tmp/isolated` works correctly
- Claude respects the isolated HOME for config

**Project Directory Access:**
- Flag: `--add-dir <path>`
- Allows access to additional directories beyond CWD
- Multiple directories can be added

**Output Format Sample:**
```json
{
  "type": "system",
  "subtype": "init",
  "cwd": "/private/tmp",
  "session_id": "ce68a5fb-ce3f-4360-9473-9b77a7c494de",
  "tools": ["Task", "Bash", "Read", "Edit", ...]
}
```

---

### Gemini CLI (v0.24.0)

**Headless JSON Output:**
- Use `gemini --output-format json "prompt"`
- Output is a single JSON object (not JSONL)
- Structure includes `session_id`, `response`, `stats`

**Session ID:**
- Field name: `session_id`
- Format: UUID (e.g., `c606d53a-25e8-41d6-82ad-747a1843bf4a`)
- Available in the response JSON

**Resume Mechanism:**
- Flag: `--resume latest` or `--resume <index>`
- Also supports `--resume <session_id>` (UUID from output)
- Use `--list-sessions` to see available sessions
- Sessions are scoped to project directory

**HOME Isolation:**
- Setting `HOME=/tmp/isolated` works correctly
- Gemini uses HOME for config storage

**Project Directory Access:**
- Flag: `--include-directories <path>`
- Can specify multiple directories (comma-separated or multiple flags)

**Output Format Sample:**
```json
{
  "session_id": "c606d53a-25e8-41d6-82ad-747a1843bf4a",
  "response": "4",
  "stats": {
    "models": {
      "gemini-2.5-flash-lite": {...},
      "gemini-3-flash-preview": {...}
    }
  }
}
```

---

### Codex CLI (v0.86.0)

**Headless JSON Output:**
- Use `codex exec --json "prompt"`
- Output is JSONL (one JSON object per line)
- Each line is an event with `type` and optional `thread_id`

**Thread ID (Session ID):**
- Field name: `thread_id`
- Format: UUID-like (e.g., `019bcd65-94ba-7830-a9cd-200fad770c8c`)
- Present in `thread.started` event

**Resume Mechanism:**
- Command: `codex exec resume <thread_id>` or `codex resume --last`
- Works with `--json` flag for JSONL output
- Thread history is preserved

**HOME Isolation:**
- Setting `HOME=/tmp/isolated` works correctly
- Shows "no credentials in temp HOME" as expected

**Project Directory Access:**
- Primary flag: `-C, --cd <path>` for working directory
- Additional flag: `--add-dir <path>` for extra writable directories
- Requires git repository (use `--skip-git-repo-check` to bypass)

**Output Format Sample (JSONL):**
```json
{"thread_id":"019bcd65-94ba-7830-a9cd-200fad770c8c","type":"thread.started"}
{"type":"turn.started"}
{"type":"item.completed","content":"..."}
{"type":"turn.completed"}
```

---

## Unexpected Behaviors Discovered

1. **Gemini uses project-scoped sessions**: Sessions are tied to the project directory, not global. This aligns with our design.

2. **Codex requires git repository**: By default, Codex won't run outside a git repo. Use `--skip-git-repo-check` for non-git directories.

3. **Claude --add-dir test false positive**: The test script incorrectly flagged `--add-dir` as failing because it searched for "error" in the output. The flag works correctly.

---

## Field Names and Flag Syntax

### Session ID Fields

| CLI | Field Name | Location |
|-----|------------|----------|
| Claude | `session_id` | Top-level in init event |
| Gemini | `session_id` | Top-level in response JSON |
| Codex | `thread_id` | In `thread.started` event |

### Resume Flags

| CLI | Flag Syntax | Notes |
|-----|-------------|-------|
| Claude | `--resume <uuid>` | Direct session ID |
| Gemini | `--resume latest` or `--resume <n>` or `--resume <uuid>` | Index, "latest", or UUID |
| Codex | `exec resume <uuid>` or `resume --last` | Subcommand, not flag |

### Additional Directory Flags

| CLI | Flag | Notes |
|-----|------|-------|
| Claude | `--add-dir <path>` | Multiple allowed |
| Gemini | `--include-directories <path>` | Array/multiple |
| Codex | `--add-dir <path>`, `--cd <path>` | --cd sets working dir, --add-dir adds writable dirs |

---

## Performance Characteristics

| CLI | Startup Time | Typical Response Time |
|-----|--------------|----------------------|
| Claude | ~1-2s | 5-30s depending on task |
| Gemini | ~1-2s | 2-5s for simple queries |
| Codex | ~1s | 5-20s depending on task |

---

## Security Considerations

1. **HOME Isolation**: All CLIs correctly respect HOME directory override. This enables running with isolated credentials.

2. **Workspace Trust**: Claude may prompt for workspace trust in interactive mode. Use `--print` mode to bypass.

3. **Git Requirements**: Codex's git repo requirement adds a layer of safety but needs handling for non-git contexts.

---

## Decision: PROCEED

Based on RCT findings:

- ✅ All critical capabilities work as documented
- ✅ Session management works for all CLIs
- ✅ HOME isolation enables credential separation
- ✅ Additional directory access works for all CLIs

**Recommendation**: Proceed to Phase 1 (Test Scaffolding)

---

## Updates to Architecture

No changes needed to `cli-agents-architecture.md`. The LocalService pattern is confirmed as appropriate.

---

## Updates to Spec

The capabilities matrix in `cli-agents-spec.md` should be updated with the actual results above.
