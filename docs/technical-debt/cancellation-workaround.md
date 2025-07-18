# Technical Debt: Adapter-Specific Cancellation Workaround

**Created:** 2025-01-18
**Target Removal:** Q3 2025 or when MCP bug is fixed
**Severity:** High
**Owner:** TBD

## Summary

We're using adapter-specific monkey patches to work around a bug in the Python MCP library where cancellations cause double responses or server crashes. While functional, this approach creates maintenance burden and risk.

## Current Implementation

Each adapter has a `cancel_aware_flow.py` that patches its async methods to handle `asyncio.CancelledError`:
- **Grok**: Wraps `generate()` method
- **OpenAI**: Patches `BackgroundFlowStrategy.execute()` for polling
- **Vertex**: No-op (handles cancellation natively)

Patches are applied via imports in each adapter's `__init__.py`.

## Problems

1. **Easy to forget** for new adapters
2. **Import-based side effects** are fragile
3. **Inconsistent patterns** across adapters
4. **No enforcement mechanism**

## Interim Mitigations

1. ✅ **Documentation** added to `BaseAdapter` class
2. ✅ **Test template** created at `tests/unit/adapters/test_cancellation_template.py`
3. ⚠️  **Missing tests** for Grok and OpenAI adapters

## Exit Criteria

Remove this workaround when ANY of:
- MCP Python library fixes the cancellation bug
- We reach Q3 2025
- We find a critical issue that forces earlier refactoring

## Tracking

- **MCP Bug Report:** Included in PR
- **MCP PR:** https://github.com/modelcontextprotocol/python-sdk/pull/1153
- **Our Issue:** Track in this document

## Refactoring Plan

When removing:
1. Delete all `cancel_aware_flow.py` files
2. Remove imports from adapter `__init__.py` files
3. Remove warning from `BaseAdapter`
4. Keep the cancellation tests (they're still valuable)
5. Verify MCP library version >= X.Y.Z (with fix)

## Action Items

- [ ] Add cancellation tests for Grok adapter
- [ ] Add cancellation tests for OpenAI adapter  
- [ ] Set calendar reminder for Q3 2025 review
- [ ] Monitor MCP library releases for fix