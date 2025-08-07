#!/usr/bin/env python3
"""Comprehensive benchmarking suite for git hook optimization strategies.

This script measures the actual performance impact of different optimization approaches
for high-frequency CLI hook execution.
"""

import sys
import time
import subprocess
import statistics
from pathlib import Path
from typing import List, Dict
import json


class HookBenchmark:
    """Benchmark different hook implementation strategies."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.results = {}
        self.warmup_runs = 2
        self.benchmark_runs = 10

    def run_strategy_benchmark(
        self, name: str, command: List[str], timeout: float = 10.0
    ) -> Dict[str, float]:
        """Benchmark a specific hook strategy."""
        print(f"\n=== Benchmarking {name} ===")
        times = []
        failures = 0

        # Warmup runs
        for _ in range(self.warmup_runs):
            try:
                subprocess.run(
                    command, cwd=self.project_root, timeout=timeout, capture_output=True
                )
            except (subprocess.TimeoutExpired, subprocess.SubprocessError):
                pass

        # Actual benchmark runs
        for i in range(self.benchmark_runs):
            start_time = time.time()
            try:
                result = subprocess.run(
                    command,
                    cwd=self.project_root,
                    timeout=timeout,
                    capture_output=True,
                    text=True,
                )
                elapsed = (time.time() - start_time) * 1000
                times.append(elapsed)
                print(f"  Run {i+1}: {elapsed:.1f}ms")

                if result.returncode != 0:
                    failures += 1

            except subprocess.TimeoutExpired:
                elapsed = timeout * 1000
                times.append(elapsed)
                failures += 1
                print(f"  Run {i+1}: TIMEOUT ({timeout}s)")
            except subprocess.SubprocessError as e:
                failures += 1
                print(f"  Run {i+1}: ERROR {e}")

        if not times:
            return {"error": "No successful runs"}

        stats = {
            "mean": statistics.mean(times),
            "median": statistics.median(times),
            "min": min(times),
            "max": max(times),
            "stdev": statistics.stdev(times) if len(times) > 1 else 0,
            "failures": failures,
            "success_rate": (len(times) - failures) / len(times) * 100,
        }

        print(f"  Mean: {stats['mean']:.1f}ms ± {stats['stdev']:.1f}ms")
        print(f"  Range: {stats['min']:.1f}ms - {stats['max']:.1f}ms")
        print(f"  Success rate: {stats['success_rate']:.1f}%")

        return stats

    def benchmark_all_strategies(self):
        """Benchmark all available hook strategies."""

        # Strategy 1: Ultra-minimal urllib approach
        minimal_script = self.project_root / "scripts" / "minimal-hook-benchmark.py"
        if not minimal_script.exists():
            self._create_minimal_hook(minimal_script)

        self.results["minimal_urllib"] = self.run_strategy_benchmark(
            "Minimal urllib hook", ["python3", str(minimal_script)]
        )

        # Strategy 2: Fast commit module with direct python
        fast_commit_path = (
            self.project_root / "mcp_the_force" / "history" / "fast_commit.py"
        )
        if fast_commit_path.exists():
            self.results["fast_commit_direct"] = self.run_strategy_benchmark(
                "Fast commit (direct python)",
                [
                    "python3",
                    "-c",
                    f"""
import sys
sys.path.insert(0, '{self.project_root}')
from mcp_the_force.history.fast_commit import record_commit_fast
record_commit_fast()
""",
                ],
            )

        # Strategy 3: Optimized standalone script
        optimized_script = self.project_root / "scripts" / "optimized-commit-hook.py"
        if optimized_script.exists():
            self.results["optimized_script"] = self.run_strategy_benchmark(
                "Optimized standalone script", ["python3", str(optimized_script)]
            )

        # Strategy 4: uv run with optimizations
        self.results["uv_optimized"] = self.run_strategy_benchmark(
            "uv run with optimizations",
            [
                "env",
                "VIRTUAL_ENV=",
                "uv",
                "run",
                "--no-sync",
                "--python",
                "python3",
                "-m",
                "mcp_the_force.history.fast_commit",
            ],
        )

        # Strategy 5: Standard commit module
        self.results["standard_commit"] = self.run_strategy_benchmark(
            "Standard commit module",
            ["python3", "-m", "mcp_the_force.history.commit"],
            timeout=15.0,
        )

        # Strategy 6: Current uv approach
        self.results["current_uv"] = self.run_strategy_benchmark(
            "Current uv approach",
            ["uv", "run", "python", "-m", "mcp_the_force.history.commit"],
            timeout=15.0,
        )

    def _create_minimal_hook(self, script_path: Path):
        """Create ultra-minimal hook for benchmarking."""
        content = '''#!/usr/bin/env python3
"""Ultra-minimal git hook with zero external dependencies."""

import os
import sys
import subprocess
import json
import time
import urllib.request
import urllib.error

def record_commit_minimal():
    """Record commit with absolute minimal dependencies."""
    try:
        # Get commit info with timeouts
        result = subprocess.run(['git', 'rev-parse', 'HEAD'], 
                              capture_output=True, text=True, timeout=1)
        if result.returncode != 0:
            return False
            
        commit_sha = result.stdout.strip()
        
        # Lightweight payload
        payload = {
            "commit_sha": commit_sha,
            "timestamp": int(time.time()),
            "project": os.path.basename(os.getcwd()),
            "type": "commit"
        }
        
        # Simulate HTTP POST (no actual network call for benchmarking)
        data = json.dumps(payload).encode('utf-8')
        return True
            
    except Exception:
        return False

if __name__ == "__main__":
    record_commit_minimal()
'''
        script_path.write_text(content)
        script_path.chmod(0o755)

    def analyze_results(self):
        """Analyze and compare benchmark results."""
        print("\n" + "=" * 60)
        print("PERFORMANCE ANALYSIS")
        print("=" * 60)

        if not self.results:
            print("No benchmark results available")
            return

        # Sort by mean execution time
        sorted_results = sorted(
            [
                (name, stats)
                for name, stats in self.results.items()
                if "error" not in stats
            ],
            key=lambda x: x[1]["mean"],
        )

        if not sorted_results:
            print("All strategies failed")
            return

        fastest_name, fastest_stats = sorted_results[0]
        print(f"\n🏆 FASTEST: {fastest_name}")
        print(f"   Mean: {fastest_stats['mean']:.1f}ms")
        print(f"   Range: {fastest_stats['min']:.1f}-{fastest_stats['max']:.1f}ms")

        print("\n📊 PERFORMANCE RANKING:")
        for i, (name, stats) in enumerate(sorted_results, 1):
            speedup = fastest_stats["mean"] / stats["mean"]
            print(
                f"   {i:2d}. {name:25s} {stats['mean']:6.1f}ms  ({speedup:4.1f}x slower than fastest)"
            )

        print("\n🎯 HIGH-FREQUENCY IMPACT (100 executions):")
        for name, stats in sorted_results[:3]:
            total_time = stats["mean"] * 100 / 1000  # Convert to seconds
            print(f"   {name:25s} {total_time:5.1f}s total")

        # Identify critical issues
        print("\n⚠️  CRITICAL ISSUES:")
        for name, stats in self.results.items():
            if "error" in stats:
                print(f"   {name}: FAILED - {stats['error']}")
            elif stats.get("success_rate", 100) < 90:
                print(f"   {name}: Low success rate ({stats['success_rate']:.1f}%)")
            elif stats.get("mean", 0) > 1000:
                print(f"   {name}: Very slow ({stats['mean']:.1f}ms)")

    def export_results(self, output_file: Path):
        """Export detailed results to JSON."""
        with open(output_file, "w") as f:
            json.dump(
                {
                    "timestamp": int(time.time()),
                    "project_root": str(self.project_root),
                    "benchmark_config": {
                        "warmup_runs": self.warmup_runs,
                        "benchmark_runs": self.benchmark_runs,
                    },
                    "results": self.results,
                },
                f,
                indent=2,
            )

        print(f"\n📁 Results exported to: {output_file}")


def main():
    """Run comprehensive hook performance benchmark."""
    if len(sys.argv) > 1:
        project_root = Path(sys.argv[1]).resolve()
    else:
        project_root = Path(__file__).parent.parent

    if not project_root.exists():
        print(f"Error: Project root {project_root} does not exist")
        sys.exit(1)

    print("🚀 Git Hook Performance Benchmark")
    print(f"Project: {project_root}")
    print(f"Python: {sys.version.split()[0]}")

    benchmark = HookBenchmark(project_root)
    benchmark.benchmark_all_strategies()
    benchmark.analyze_results()

    # Export results
    results_file = project_root / "benchmark_results.json"
    benchmark.export_results(results_file)


if __name__ == "__main__":
    main()
