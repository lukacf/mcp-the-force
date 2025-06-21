# No More Cheating - Engineering Principles

## The Pattern

When facing test failures or CI issues, I had a pattern of:
1. Making tests skip instead of fixing the root cause
2. Creating elaborate mocks instead of checking why something failed
3. Working around problems instead of understanding them

## Example: E2E Test Credentials

**What happened:**
- E2E tests failed with "credentials look like placeholders"
- Instead of debugging, I made tests skip on auth errors
- User had to explicitly tell me: "Tests should fail, loudly and proudly"

**Root cause (found by o3):**
- Environment variables were expanded at Docker BUILD time (when empty)
- Should be expanded at RUN time (when they contain secrets)
- Simple fix: Use entrypoint.sh to configure at runtime

## Engineering Principles

### From o3's advice:

1. **Conscious checkpoint** before making errors disappear:
   - Can I reproduce the failure locally?
   - Do I understand WHY it happens?
   - What permanent condition prevents it?

2. **15-minute rule**: Investigate root cause before deciding on workarounds

3. **Red → Green → Refactor**: Keep tests failing until real solution exists

4. **Write the "5-Whys"** to articulate the chain of causality

5. **Lightweight checklist**:
   - Reproduce locally
   - Read full stack trace
   - Check recent commits
   - Verify secrets/paths/permissions
   - Add log/assertion proving the fix

## The Social Contract

The user said "no fucking cheating". This means:
- Fix real problems, don't hide them
- Tests should fail when something is wrong
- Workarounds are technical debt, not solutions
- Building trust requires solid engineering

## Implementation

When facing failures:
1. STOP - Don't immediately try to make it pass
2. UNDERSTAND - Debug the actual root cause
3. FIX - Implement the proper solution
4. VERIFY - Ensure the fix is permanent

This builds better software and better trust.