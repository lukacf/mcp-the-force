#!/usr/bin/env python3
"""Generate complete performance matrix for all tree implementations."""

import sys

sys.path.append(".")
from tree_benchmark import benchmark_implementations


def main():
    # Run benchmark and collect detailed results
    results = benchmark_implementations()

    print("COMPLETE TOKEN PERFORMANCE MATRIX")
    print("=" * 80)
    print()

    # Get all test case names and implementation names
    test_cases = list(results.keys())
    if test_cases:
        impl_names = list(results[test_cases[0]].keys())

        # Create header
        print(f'{"Test Case":<25}', end="")
        for impl in impl_names:
            print(f"{impl:>12}", end="")
        print()
        print("-" * (25 + 12 * len(impl_names)))

        # Print data for each test case
        for test_case in test_cases:
            print(f"{test_case:<25}", end="")
            for impl in impl_names:
                if impl in results[test_case] and "tokens" in results[test_case][impl]:
                    tokens = results[test_case][impl]["tokens"]
                    print(f"{tokens:>12}", end="")
                else:
                    print(f'{"ERROR":>12}', end="")
            print()

    print()
    print()
    print("SAVINGS PERCENTAGE MATRIX (vs Original ASCII)")
    print("=" * 80)
    print()

    # Create savings matrix
    print(f'{"Test Case":<25}', end="")
    for impl in impl_names:
        if impl != "Original ASCII":
            print(f"{impl:>12}", end="")
    print()
    print("-" * (25 + 12 * (len(impl_names) - 1)))

    for test_case in test_cases:
        print(f"{test_case:<25}", end="")

        # Get baseline (Original ASCII)
        baseline = None
        if (
            "Original ASCII" in results[test_case]
            and "tokens" in results[test_case]["Original ASCII"]
        ):
            baseline = results[test_case]["Original ASCII"]["tokens"]

        for impl in impl_names:
            if impl != "Original ASCII":
                if (
                    impl in results[test_case]
                    and "tokens" in results[test_case][impl]
                    and baseline
                ):
                    tokens = results[test_case][impl]["tokens"]
                    savings = ((baseline - tokens) / baseline) * 100
                    print(f"{savings:>11.1f}%", end="")
                else:
                    print(f'{"N/A":>12}', end="")
        print()

    print()
    print()
    print("EXECUTION TIME MATRIX (milliseconds)")
    print("=" * 80)
    print()

    print(f'{"Test Case":<25}', end="")
    for impl in impl_names:
        print(f"{impl:>12}", end="")
    print()
    print("-" * (25 + 12 * len(impl_names)))

    for test_case in test_cases:
        print(f"{test_case:<25}", end="")
        for impl in impl_names:
            if impl in results[test_case] and "time_ms" in results[test_case][impl]:
                time_ms = results[test_case][impl]["time_ms"]
                print(f"{time_ms:>11.1f}", end="")
            else:
                print(f'{"N/A":>12}', end="")
        print()

    print()
    print()
    print("RANKING MATRIX (1=best, 5=worst by token count)")
    print("=" * 80)
    print()

    print(f'{"Test Case":<25}', end="")
    for impl in impl_names:
        print(f"{impl:>12}", end="")
    print()
    print("-" * (25 + 12 * len(impl_names)))

    for test_case in test_cases:
        print(f"{test_case:<25}", end="")

        # Get token counts and rank them
        token_counts = []
        for impl in impl_names:
            if impl in results[test_case] and "tokens" in results[test_case][impl]:
                tokens = results[test_case][impl]["tokens"]
                token_counts.append((impl, tokens))

        # Sort by token count (ascending = better)
        token_counts.sort(key=lambda x: x[1])

        # Create ranking dict
        rankings = {}
        for i, (impl, tokens) in enumerate(token_counts):
            rankings[impl] = i + 1

        # Print rankings
        for impl in impl_names:
            if impl in rankings:
                print(f"{rankings[impl]:>12}", end="")
            else:
                print(f'{"N/A":>12}', end="")
        print()

    print()
    print()
    print("WINNER ANALYSIS")
    print("=" * 80)

    # Count wins for each implementation
    wins = {impl: 0 for impl in impl_names}

    for test_case in test_cases:
        token_counts = []
        for impl in impl_names:
            if impl in results[test_case] and "tokens" in results[test_case][impl]:
                tokens = results[test_case][impl]["tokens"]
                token_counts.append((impl, tokens))

        if token_counts:
            # Winner is the one with lowest token count
            winner = min(token_counts, key=lambda x: x[1])[0]
            wins[winner] += 1

    print("\nTest Case Wins by Implementation:")
    for impl, win_count in sorted(wins.items(), key=lambda x: x[1], reverse=True):
        print(f"  {impl:<20}: {win_count} wins")

    print()
    print("FUSION TREE DOMINANCE ANALYSIS")
    print("=" * 50)

    # Show FusionTree vs UltraTree head-to-head
    for test_case in test_cases:
        if (
            "V5 FusionTree" in results[test_case]
            and "V4 UltraTree" in results[test_case]
            and "tokens" in results[test_case]["V5 FusionTree"]
            and "tokens" in results[test_case]["V4 UltraTree"]
        ):
            fusion_tokens = results[test_case]["V5 FusionTree"]["tokens"]
            ultra_tokens = results[test_case]["V4 UltraTree"]["tokens"]
            improvement = ((ultra_tokens - fusion_tokens) / ultra_tokens) * 100

            print(
                f"{test_case:<25}: FusionTree beats UltraTree by {ultra_tokens - fusion_tokens:4d} tokens ({improvement:5.1f}%)"
            )

    print()
    print("RECORD BREAKING SAVINGS")
    print("=" * 30)

    # Find the best savings for each test case
    for test_case in test_cases:
        if (
            "Original ASCII" in results[test_case]
            and "tokens" in results[test_case]["Original ASCII"]
        ):
            baseline = results[test_case]["Original ASCII"]["tokens"]

            # Find the best performer
            best_tokens = float("inf")
            best_impl = None
            for impl in impl_names:
                if (
                    impl != "Original ASCII"
                    and impl in results[test_case]
                    and "tokens" in results[test_case][impl]
                ):
                    tokens = results[test_case][impl]["tokens"]
                    if tokens < best_tokens:
                        best_tokens = tokens
                        best_impl = impl

            if best_impl:
                savings = ((baseline - best_tokens) / baseline) * 100
                print(
                    f"{test_case:<25}: {best_impl} saves {baseline - best_tokens:4d} tokens ({savings:5.1f}%)"
                )
                if best_impl == "V5 FusionTree":
                    print("                         ^^^ NEW RECORD! ^^^")


if __name__ == "__main__":
    main()
