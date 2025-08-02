#!/usr/bin/env python3
"""Ultimate analysis of all file tree algorithms including NeutrinoTree."""


def analyze_ultimate_performance():
    # Complete results from the benchmark including NeutrinoTree
    results = {
        "Small (10)": {"original": 88, "fusion": 40, "quark": 40, "neutrino": 39},
        "Medium (50)": {"original": 434, "fusion": 193, "quark": 226, "neutrino": 193},
        "Large (200)": {"original": 1764, "fusion": 597, "quark": 836, "neutrino": 597},
        "Numbered (153)": {
            "original": 1226,
            "fusion": 80,
            "quark": 162,
            "neutrino": 80,
        },
        "Real: MCP (230)": {
            "original": 2670,
            "fusion": 948,
            "quark": 897,
            "neutrino": 955,
        },
        "Real: LifeTales (814)": {
            "original": 11757,
            "fusion": 3994,
            "quark": 3887,
            "neutrino": 3186,
        },
        "Real: CandyCrush (87352)": {
            "original": 1990897,
            "fusion": 163092,
            "quark": 160011,
            "neutrino": 160979,
        },
    }

    print("🚀 ULTIMATE FILE TREE ALGORITHM ANALYSIS")
    print("=" * 60)
    print()

    # Separate synthetic vs real-world
    synthetic_tests = {k: v for k, v in results.items() if not k.startswith("Real:")}
    real_world_tests = {k: v for k, v in results.items() if k.startswith("Real:")}

    print("📊 SYNTHETIC BENCHMARKS PERFORMANCE")
    print("=" * 50)

    synthetic_wins = {"fusion": 0, "quark": 0, "neutrino": 0}

    for test, data in synthetic_tests.items():
        print(f"\n{test}:")

        # Find the winner
        algorithms = ["fusion", "quark", "neutrino"]
        tokens = [(alg, data[alg]) for alg in algorithms]
        tokens.sort(key=lambda x: x[1])
        winner = tokens[0]

        for alg, token_count in tokens:
            improvement = ((data["original"] - token_count) / data["original"]) * 100
            status = (
                "🏆 WINNER" if alg == winner[0] else f"  +{token_count - winner[1]}"
            )
            print(
                f"  {alg.capitalize():<10}: {token_count:>4} tokens ({improvement:5.1f}%) {status}"
            )

        synthetic_wins[winner[0]] += 1

    print(
        f"\nSynthetic wins: Fusion {synthetic_wins['fusion']}, Quark {synthetic_wins['quark']}, Neutrino {synthetic_wins['neutrino']}"
    )

    print("\n🌍 REAL-WORLD CODEBASE PERFORMANCE")
    print("=" * 50)

    real_world_wins = {"fusion": 0, "quark": 0, "neutrino": 0}

    for test, data in real_world_tests.items():
        print(f"\n{test}:")

        # Find the winner
        algorithms = ["fusion", "quark", "neutrino"]
        tokens = [(alg, data[alg]) for alg in algorithms]
        tokens.sort(key=lambda x: x[1])
        winner = tokens[0]

        for alg, token_count in tokens:
            improvement = ((data["original"] - token_count) / data["original"]) * 100
            status = (
                "🏆 WINNER" if alg == winner[0] else f"  +{token_count - winner[1]:,}"
            )
            print(
                f"  {alg.capitalize():<10}: {token_count:>8,} tokens ({improvement:5.1f}%) {status}"
            )

        real_world_wins[winner[0]] += 1

    print(
        f"\nReal-world wins: Fusion {real_world_wins['fusion']}, Quark {real_world_wins['quark']}, Neutrino {real_world_wins['neutrino']}"
    )

    print("\n🎯 NEUTRINOTREE THEORETICAL OPTIMALITY TEST")
    print("=" * 50)

    never_loses = True
    worst_performance = []

    for test, data in results.items():
        fusion_tokens = data["fusion"]
        quark_tokens = data["quark"]
        neutrino_tokens = data["neutrino"]

        # Check if NeutrinoTree is ever worse than BOTH competitors
        if neutrino_tokens > fusion_tokens and neutrino_tokens > quark_tokens:
            never_loses = False
            worst_performance.append(
                (test, neutrino_tokens, min(fusion_tokens, quark_tokens))
            )
            print(
                f"❌ {test}: NeutrinoTree {neutrino_tokens} vs best {min(fusion_tokens, quark_tokens)}"
            )
        elif neutrino_tokens > min(fusion_tokens, quark_tokens):
            gap = neutrino_tokens - min(fusion_tokens, quark_tokens)
            print(f"⚠️  {test}: NeutrinoTree {gap} tokens behind best")
        else:
            print(f"✅ {test}: NeutrinoTree optimal or winning")

    print(
        f"\nNeutrinoTree achieves theoretical optimality: {'YES' if never_loses else 'NO'}"
    )

    print("\n🏆 LIFETALES DEEP DIVE - NEUTRINOTREE'S MASTERPIECE")
    print("=" * 60)

    lifetales = real_world_tests["Real: LifeTales (814)"]
    neutrino_advantage_vs_quark = lifetales["quark"] - lifetales["neutrino"]
    neutrino_advantage_vs_fusion = lifetales["fusion"] - lifetales["neutrino"]

    print(f"Original ASCII:  {lifetales['original']:>6,} tokens")
    print(
        f"FusionTree:      {lifetales['fusion']:>6,} tokens ({((lifetales['original'] - lifetales['fusion']) / lifetales['original'] * 100):5.1f}% savings)"
    )
    print(
        f"QuarkTree:       {lifetales['quark']:>6,} tokens ({((lifetales['original'] - lifetales['quark']) / lifetales['original'] * 100):5.1f}% savings)"
    )
    print(
        f"NeutrinoTree:    {lifetales['neutrino']:>6,} tokens ({((lifetales['original'] - lifetales['neutrino']) / lifetales['original'] * 100):5.1f}% savings)"
    )
    print()
    print(
        f"NeutrinoTree beats QuarkTree by:  {neutrino_advantage_vs_quark:>4,} tokens ({(neutrino_advantage_vs_quark/lifetales['quark']*100):4.1f}%)"
    )
    print(
        f"NeutrinoTree beats FusionTree by: {neutrino_advantage_vs_fusion:>4,} tokens ({(neutrino_advantage_vs_fusion/lifetales['fusion']*100):4.1f}%)"
    )

    print("\n🎖️ FINAL SCOREBOARD")
    print("=" * 30)

    total_fusion_wins = synthetic_wins["fusion"] + real_world_wins["fusion"]
    total_quark_wins = synthetic_wins["quark"] + real_world_wins["quark"]
    total_neutrino_wins = synthetic_wins["neutrino"] + real_world_wins["neutrino"]

    algorithms_scores = [
        ("NeutrinoTree", total_neutrino_wins),
        ("QuarkTree", total_quark_wins),
        ("FusionTree", total_fusion_wins),
    ]
    algorithms_scores.sort(key=lambda x: x[1], reverse=True)

    for i, (alg, wins) in enumerate(algorithms_scores):
        medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉"
        print(f"{medal} {alg}: {wins}/7 wins")

    print("\n🔥 FINAL RECOMMENDATION")
    print("=" * 30)

    winner = algorithms_scores[0]

    if winner[0] == "NeutrinoTree":
        print("👑 ADOPT NEUTRINOTREE!")
        print("✅ Wins or ties most test cases")
        print("✅ Achieves near-theoretical optimality")
        print("✅ Massive gains on complex real codebases")
        print("✅ Never catastrophically fails")
        print("⚠️  Higher computational cost (tri-candidate testing)")
        print()
        print("NeutrinoTree represents the state-of-the-art in file tree compression.")
        print("The 'try everything, pick shortest' approach delivers optimal results.")
    elif winner[0] == "QuarkTree":
        print("👑 ADOPT QUARKTREE!")
        print("✅ Strong performance on all real codebases")
        print("✅ Good balance of complexity vs performance")
    else:
        print("👑 KEEP FUSIONTREE!")
        print("✅ Simpler implementation")
        print("✅ Good overall performance")


if __name__ == "__main__":
    analyze_ultimate_performance()
