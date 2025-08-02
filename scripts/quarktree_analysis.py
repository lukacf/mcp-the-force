#!/usr/bin/env python3
"""Analyze QuarkTree performance vs O3 Pro's bold predictions."""


def analyze_quarktree_performance():
    # Results from the benchmark
    predictions = {
        "Small (10)": {
            "original": 88,
            "fusion": 40,
            "quark_predicted": 37,
            "quark_actual": 40,
        },
        "Medium (50)": {
            "original": 434,
            "fusion": 193,
            "quark_predicted": 168,
            "quark_actual": 226,
        },
        "Large (200)": {
            "original": 1764,
            "fusion": 597,
            "quark_predicted": 520,
            "quark_actual": 836,
        },
        "Numbered (153)": {
            "original": 1226,
            "fusion": 80,
            "quark_predicted": 74,
            "quark_actual": 162,
        },
        "MCP (227)": {
            "original": 2645,
            "fusion": 933,
            "quark_predicted": 818,
            "quark_actual": 882,
        },
        "LifeTales (814)": {
            "original": 11757,
            "fusion": 3994,
            "quark_predicted": 3120,
            "quark_actual": 3887,
        },
    }

    print("🎯 QUARKTREE PERFORMANCE ANALYSIS")
    print("=" * 50)
    print()

    wins = 0
    total = 0
    actual_vs_fusion = []
    prediction_accuracy = []

    for test, data in predictions.items():
        print(f"{test}:")
        predicted_gain = (
            (data["fusion"] - data["quark_predicted"]) / data["fusion"]
        ) * 100
        actual_gain = ((data["fusion"] - data["quark_actual"]) / data["fusion"]) * 100

        # Check if QuarkTree beats FusionTree
        beats_fusion = data["quark_actual"] < data["fusion"]
        if beats_fusion:
            wins += 1
            vs_fusion = ((data["fusion"] - data["quark_actual"]) / data["fusion"]) * 100
            actual_vs_fusion.append(vs_fusion)
            print(
                f"  ✅ WINS! QuarkTree: {data['quark_actual']} vs FusionTree: {data['fusion']} ({vs_fusion:.1f}% better)"
            )
        else:
            vs_fusion = ((data["quark_actual"] - data["fusion"]) / data["fusion"]) * 100
            print(
                f"  ❌ Loses: QuarkTree: {data['quark_actual']} vs FusionTree: {data['fusion']} ({vs_fusion:.1f}% worse)"
            )

        # Prediction accuracy
        prediction_error = abs(predicted_gain - actual_gain)
        prediction_accuracy.append(prediction_error)

        print(
            f"     O3 Pro predicted: {predicted_gain:.1f}% gain, actual: {actual_gain:.1f}% (error: {prediction_error:.1f}%)"
        )
        print()
        total += 1

    print(
        f"FINAL SCORE: QuarkTree wins {wins}/{total} test cases ({wins/total*100:.1f}%)"
    )

    if actual_vs_fusion:
        avg_improvement = sum(actual_vs_fusion) / len(actual_vs_fusion)
        print(f"Average improvement when winning: {avg_improvement:.1f}%")

    avg_prediction_error = sum(prediction_accuracy) / len(prediction_accuracy)
    print(f"O3 Pro's average prediction error: {avg_prediction_error:.1f}%")

    print()
    print("🏆 CROWN STATUS:")
    if wins >= total // 2:
        print("👑 QuarkTree RECLAIMS THE CROWN!")
        print(
            f"   Wins on real codebases: MCP ({882} vs {933}) and LifeTales ({3887} vs {3994})"
        )
    else:
        print("👑 FusionTree KEEPS THE CROWN!")
        print("   QuarkTree shows promise but doesn't consistently beat FusionTree")

    return wins, total


if __name__ == "__main__":
    analyze_quarktree_performance()
