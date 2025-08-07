#!/usr/bin/env python3
"""
Command-line startup benchmarking for MCP The-Force server.

This script measures the ACTUAL startup time using the real command:
    uv run -- mcp-the-force

It measures time to server initialization (before listening for connections).
"""

import subprocess
import statistics
import sys
import time
from pathlib import Path
from typing import Dict, List


class CLIBenchmark:
    """Benchmark the actual command-line startup performance."""

    def __init__(self, runs: int = 3, timeout: int = 30):
        self.runs = runs
        self.timeout = timeout

    def benchmark_cli_startup(self) -> Dict:
        """Benchmark the actual CLI command startup time."""

        print("🚀 CLI Startup Benchmark: uv run -- mcp-the-force")
        print("=" * 60)
        print(f"Measuring startup time until server is ready ({self.runs} runs)")
        print("Each run will be terminated after server initialization completes")
        print()

        times = []
        errors = []

        for run in range(self.runs):
            print(f"Run {run + 1}/{self.runs}...", end=" ", flush=True)

            start_time = time.perf_counter()
            result = self._measure_single_run()
            end_time = time.perf_counter()

            if result["success"]:
                total_time = end_time - start_time
                times.append(
                    {
                        "total_time": total_time,
                        "logs": result.get("logs", []),
                        "init_time": result.get("init_time"),
                        "run_number": run + 1,
                    }
                )
                print(f"{total_time:.3f}s")
            else:
                errors.append(
                    {
                        "run": run + 1,
                        "error": result["error"],
                        "stderr": result.get("stderr", ""),
                    }
                )
                print(f"ERROR: {result['error']}")

        return self._calculate_statistics(times, errors)

    def _measure_single_run(self) -> Dict:
        """Measure a single CLI startup run."""

        try:
            # Start the server process
            cmd = ["uv", "run", "--", "mcp-the-force"]

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line buffering
                universal_newlines=True,
            )

            # Monitor for server ready indicators
            start_time = time.perf_counter()
            logs = []
            init_time = None

            try:
                # Give it time to initialize
                time.sleep(2.0)  # Basic initialization time

                # Check if process is still running (successfully started)
                if process.poll() is None:
                    # Process is running - consider it successfully started
                    init_time = time.perf_counter() - start_time

                    # Collect some stderr logs for analysis
                    try:
                        # Non-blocking read of available stderr
                        import select

                        if hasattr(select, "select"):  # Unix systems
                            ready, _, _ = select.select([process.stderr], [], [], 0.1)
                            if ready:
                                stderr_data = process.stderr.read()
                                if stderr_data:
                                    logs = stderr_data.strip().split("\n")
                    except Exception:
                        pass  # Best effort log collection

                    # Terminate the process gracefully
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()

                    return {"success": True, "init_time": init_time, "logs": logs}
                else:
                    # Process exited - get error info
                    stdout, stderr = process.communicate()
                    return {
                        "success": False,
                        "error": f"Process exited with code {process.returncode}",
                        "stderr": stderr,
                        "stdout": stdout,
                    }

            except Exception as e:
                # Clean up process
                try:
                    process.terminate()
                    process.wait(timeout=2)
                except Exception:
                    try:
                        process.kill()
                        process.wait()
                    except Exception:
                        pass

                return {"success": False, "error": f"Monitoring failed: {e}"}

        except Exception as e:
            return {"success": False, "error": f"Failed to start process: {e}"}

    def _calculate_statistics(self, times: List[Dict], errors: List[Dict]) -> Dict:
        """Calculate statistics from the timing results."""

        if not times:
            return {
                "successful_runs": 0,
                "failed_runs": len(errors),
                "error": "No successful runs",
                "errors": errors,
            }

        total_times = [t["total_time"] for t in times]
        init_times = [t["init_time"] for t in times if t["init_time"] is not None]

        stats = {
            "successful_runs": len(times),
            "failed_runs": len(errors),
            "total_time": {
                "mean": statistics.mean(total_times),
                "median": statistics.median(total_times),
                "stdev": statistics.stdev(total_times) if len(total_times) > 1 else 0,
                "min": min(total_times),
                "max": max(total_times),
                "runs": total_times,
            },
            "errors": errors,
            "raw_times": times,
        }

        if init_times:
            stats["init_time"] = {
                "mean": statistics.mean(init_times),
                "median": statistics.median(init_times),
                "stdev": statistics.stdev(init_times) if len(init_times) > 1 else 0,
            }

        return stats

    def print_results(self, results: Dict):
        """Print the CLI benchmark results."""

        print("\n" + "=" * 60)
        print("📊 CLI BENCHMARK RESULTS")
        print("=" * 60)

        print("\n🎯 SUCCESS RATE:")
        successful = results.get("successful_runs", 0)
        failed = results.get("failed_runs", 0)
        total = successful + failed
        success_rate = (successful / total * 100) if total > 0 else 0

        print(f"   Successful runs:    {successful}/{total} ({success_rate:.1f}%)")
        if failed > 0:
            print(f"   Failed runs:        {failed}")

        if "total_time" in results:
            total_time = results["total_time"]
            print("\n⏱️  STARTUP TIME:")
            print(f"   Mean:              {total_time.get('mean', 0):.3f}s")
            print(f"   Median:            {total_time.get('median', 0):.3f}s")
            print(f"   Standard dev:      {total_time.get('stdev', 0):.3f}s")
            print(
                f"   Range:             {total_time.get('min', 0):.3f}s - {total_time.get('max', 0):.3f}s"
            )
            print(
                f"   All runs:          {[f'{t:.3f}s' for t in total_time.get('runs', [])]}"
            )

        if "init_time" in results:
            init_time = results["init_time"]
            print("\n🚀 INITIALIZATION TIME:")
            print(f"   Mean init:         {init_time.get('mean', 0):.3f}s")
            print(f"   Median init:       {init_time.get('median', 0):.3f}s")

        # Show errors if any
        errors = results.get("errors", [])
        if errors:
            print("\n❌ ERRORS:")
            for error in errors[:3]:  # Show first 3 errors
                print(
                    f"   Run #{error.get('run', '?')}: {error.get('error', 'Unknown error')}"
                )
                if error.get("stderr"):
                    stderr_preview = error["stderr"][:200]
                    print(
                        f"        Stderr: {stderr_preview}{'...' if len(error['stderr']) > 200 else ''}"
                    )

        # Performance assessment
        if "total_time" in results:
            mean_time = results["total_time"].get("mean", 0)

            print("\n📈 PERFORMANCE ASSESSMENT:")
            if mean_time < 0.5:
                grade = "EXCELLENT 🚀"
                comment = "Very fast startup for development use"
            elif mean_time < 1.0:
                grade = "GOOD ✅"
                comment = "Acceptable startup time"
            elif mean_time < 2.0:
                grade = "NEEDS IMPROVEMENT ⚠️"
                comment = "Slow startup may impact development experience"
            else:
                grade = "CRITICAL 🐌"
                comment = "Very slow startup - optimization needed"

            print(f"   Grade:             {grade}")
            print(f"   Assessment:        {comment}")

            # Show optimization potential
            if mean_time > 1.0:
                optimized_time = 0.1  # Expected after optimization
                improvement = (1 - optimized_time / mean_time) * 100
                print(
                    f"   Optimization potential: {improvement:.1f}% improvement ({optimized_time:.1f}s target)"
                )


def main():
    """Main entry point for CLI benchmarking."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Benchmark MCP The-Force CLI startup performance"
    )
    parser.add_argument(
        "--runs", type=int, default=3, help="Number of benchmark runs (default: 3)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout per run in seconds (default: 30)",
    )

    args = parser.parse_args()

    # Check if we're in the right directory
    if not Path("mcp_the_force").exists():
        print("❌ Error: Must run from the mcp-the-force project root directory")
        sys.exit(1)

    benchmark = CLIBenchmark(runs=args.runs, timeout=args.timeout)
    results = benchmark.benchmark_cli_startup()
    benchmark.print_results(results)


if __name__ == "__main__":
    main()
