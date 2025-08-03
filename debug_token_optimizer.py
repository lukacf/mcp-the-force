#!/usr/bin/env python3
"""
Standalone debugging script for TokenBudgetOptimizer.

This script runs outside MCP to debug token allocation issues.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

from mcp_the_force.optimization.token_budget_optimizer import TokenBudgetOptimizer
from mcp_the_force.utils.token_counter import count_tokens
from mcp_the_force.utils.stable_list_cache import StableListCache


async def debug_token_optimization():
    """Debug the token optimization process step by step."""

    # Configure logging for detailed output
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    print("🔍 DEBUGGING TOKEN BUDGET OPTIMIZER")
    print("=" * 60)

    # Test parameters matching the failing case - use current project
    context_path = "/Users/luka/src/cc/finally-fix-context-problem"
    session_id = "debug-session-001"
    model_limit = 200_000  # o3 context window
    fixed_reserve = 4_000  # Reserve for response

    print(f"📁 Context Path: {context_path}")
    print(f"🧠 Model Limit: {model_limit:,} tokens")
    print(f"🔒 Fixed Reserve: {fixed_reserve:,} tokens")
    print(f"💳 Available Budget: {model_limit - fixed_reserve:,} tokens")
    print()

    if not os.path.exists(context_path):
        print(f"❌ Context path does not exist: {context_path}")
        return

    # Step 1: Create optimizer
    print("1️⃣ CREATING OPTIMIZER")
    print("-" * 30)

    optimizer = TokenBudgetOptimizer(
        model_limit=model_limit,
        fixed_reserve=fixed_reserve,
        session_id=session_id,
        context_paths=[context_path],
        priority_paths=[],
        developer_prompt="Debug test",
        instructions="Test instructions",
        output_format="Debug output",
        project_name="debug-test",
        tool_name="debug_tool",
    )

    print("✅ Optimizer created")
    print()

    # Step 2: Check file gathering
    print("2️⃣ GATHERING FILES")
    print("-" * 30)

    from mcp_the_force.utils.fs import gather_file_paths_async

    file_paths = await gather_file_paths_async([context_path])
    print(f"📊 Total files found: {len(file_paths)}")

    # Show file size distribution
    file_sizes = []
    text_files = 0

    for path in file_paths[:20]:  # Sample first 20 files
        try:
            size = os.path.getsize(path)
            file_sizes.append((path, size))

            # Check if it's a text file we'd process
            if Path(path).suffix.lower() in [
                ".py",
                ".js",
                ".ts",
                ".tsx",
                ".go",
                ".java",
                ".cpp",
                ".c",
                ".html",
                ".css",
                ".json",
                ".md",
                ".txt",
                ".yaml",
                ".yml",
            ]:
                text_files += 1

        except Exception as e:
            print(f"⚠️  Error checking {path}: {e}")

    file_sizes.sort(key=lambda x: x[1])  # Sort by size

    print(f"📝 Estimated text files (first 20): {text_files}")
    print("📐 Smallest files (first 10):")
    for path, size in file_sizes[:10]:
        print(f"   {size:,} bytes - {Path(path).name}")
    print()

    # Step 3: Test token counting on small files
    print("3️⃣ TOKEN COUNTING SAMPLE")
    print("-" * 30)

    from mcp_the_force.utils.context_builder import count_tokens_from_file

    for path, size in file_sizes[:5]:
        try:
            tokens = count_tokens_from_file(path)
            ratio = tokens / size if size > 0 else 0
            print(f"📄 {Path(path).name}")
            print(f"   Size: {size:,} bytes")
            print(f"   Tokens: {tokens:,}")
            print(f"   Ratio: {ratio:.3f} tokens/byte")
            print()
        except Exception as e:
            print(f"⚠️  Error counting tokens for {path}: {e}")

    # Step 4: Test build_context_with_stable_list directly
    print("4️⃣ TESTING CONTEXT BUILDER DIRECTLY")
    print("-" * 30)

    from mcp_the_force.utils.context_builder import build_context_with_stable_list

    test_budget = model_limit - fixed_reserve  # 196,000 tokens
    print(f"🎯 Test budget: {test_budget:,} tokens")

    cache = StableListCache()

    try:
        inline_files, overflow_files, file_tree = await build_context_with_stable_list(
            context_paths=[context_path],
            session_id=session_id,
            cache=cache,
            token_budget=test_budget,
            priority_context=[],
        )

        print(f"📥 Inline files: {len(inline_files)}")
        print(f"📤 Overflow files: {len(overflow_files)}")

        if inline_files:
            print(
                f"🔍 First inline file: {inline_files[0][0] if inline_files[0] else 'Unknown'}"
            )

        # Calculate actual tokens used by inline files
        inline_tokens = 0
        for file_info in inline_files:
            if isinstance(file_info, tuple) and len(file_info) >= 2:
                content = file_info[1]
                tokens = count_tokens([content])
                inline_tokens += tokens

        print(f"💰 Actual inline tokens: {inline_tokens:,}")
        print(f"📊 Budget utilization: {inline_tokens / test_budget * 100:.1f}%")

    except Exception as e:
        print(f"❌ Error in context builder: {e}")
        import traceback

        traceback.print_exc()

    print()

    # Step 5: Run full optimization
    print("5️⃣ RUNNING FULL OPTIMIZATION")
    print("-" * 30)

    try:
        plan = await optimizer.optimize()

        print("📋 OPTIMIZATION RESULTS:")
        print(f"   Inline files: {len(plan.inline_files)}")
        print(f"   Overflow files: {len(plan.overflow_files)}")
        print(f"   Total prompt tokens: {plan.total_prompt_tokens:,}")
        print(f"   Iterations: {plan.iterations}")
        print(
            f"   Budget utilization: {plan.total_prompt_tokens / model_limit * 100:.1f}%"
        )

        # Show which files made it inline
        print("\n📥 INLINE FILES:")
        for i, file_info in enumerate(plan.inline_files[:10]):  # Show first 10
            if hasattr(file_info, "path"):
                path = file_info.path
                size = file_info.size
                tokens = file_info.tokens
            elif isinstance(file_info, tuple):
                path = file_info[0] if len(file_info) > 0 else "Unknown"
                size = os.path.getsize(path) if os.path.exists(path) else 0
                tokens = count_tokens_from_file(path) if os.path.exists(path) else 0
            else:
                path = str(file_info)
                size = 0
                tokens = 0

            print(f"   {i+1}. {Path(path).name} ({size:,} bytes, {tokens:,} tokens)")

        if len(plan.inline_files) > 10:
            print(f"   ... and {len(plan.inline_files) - 10} more")

    except Exception as e:
        print(f"❌ Error in optimization: {e}")
        import traceback

        traceback.print_exc()

    cache.close()

    print("\n🏁 DEBUGGING COMPLETE")


if __name__ == "__main__":
    asyncio.run(debug_token_optimization())
