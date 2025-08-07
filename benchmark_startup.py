#!/usr/bin/env python3
"""Comprehensive startup performance benchmarking for MCP The-Force server.

This script measures:
1. Total startup time from command invocation to server ready
2. Import chain breakdown using Python's -X importtime
3. Module-level timing for adapters vs core imports
4. Identification of TOP 3 bottlenecks for optimization

Usage:
    python benchmark_startup.py
    python benchmark_startup.py --runs 5
    python benchmark_startup.py --detailed-imports
"""

import argparse
import json
import re
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List


class StartupBenchmark:
    """Comprehensive startup performance benchmarking suite."""

    def __init__(self, runs: int = 3, detailed_imports: bool = False):
        self.runs = runs
        self.detailed_imports = detailed_imports
        self.results = {}

    def run_full_benchmark(self) -> Dict:
        """Run the complete benchmarking suite."""
        print("🚀 MCP The-Force Startup Performance Benchmark")
        print("=" * 60)

        # 1. Measure total startup time
        print(f"\n1. Measuring total startup time ({self.runs} runs)...")
        startup_times = self._measure_startup_time()

        # 2. Analyze import performance
        print("\n2. Analyzing import performance...")
        import_analysis = self._analyze_import_performance()

        # 3. Profile memory usage
        print("\n3. Profiling memory usage...")
        memory_profile = self._profile_memory_usage()

        # 4. Identify bottlenecks
        print("\n4. Identifying performance bottlenecks...")
        bottlenecks = self._identify_bottlenecks(import_analysis)

        self.results = {
            "startup_times": startup_times,
            "import_analysis": import_analysis,
            "memory_profile": memory_profile,
            "bottlenecks": bottlenecks,
            "recommendations": self._generate_recommendations(bottlenecks),
        }

        self._print_summary()
        return self.results

    def _measure_startup_time(self) -> Dict:
        """Measure total startup time from command to server ready."""
        times = []

        for run in range(self.runs):
            print(f"  Run {run + 1}/{self.runs}...", end=" ", flush=True)

            # Create a test script that imports server and measures to "server ready"
            test_script = f"""
import sys
sys.path.insert(0, "{Path.cwd()}")
import time
start_time = time.perf_counter()

# Measure time to import main components
from mcp_the_force.main_wrapper import ensure_config_exists
config_time = time.perf_counter()

# Import server components (this is where the heavy lifting happens)
from mcp_the_force import server
import_time = time.perf_counter()

# Measure time to initialize (without actually starting server)
from mcp_the_force.tools.integration import register_all_tools
from fastmcp import FastMCP
mcp = FastMCP("benchmark-test")

# This is where tool registration happens (includes adapter imports)
register_all_tools(mcp)
ready_time = time.perf_counter()

print(f"CONFIG_TIME:{{config_time - start_time:.4f}}")
print(f"IMPORT_TIME:{{import_time - config_time:.4f}}")
print(f"READY_TIME:{{ready_time - import_time:.4f}}")
print(f"TOTAL_TIME:{{ready_time - start_time:.4f}}")
"""

            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(test_script)
                test_file = f.name

            try:
                # Run the test script and capture output
                result = subprocess.run(
                    [sys.executable, test_file],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.returncode == 0:
                    # Parse timing results
                    output_lines = result.stdout.strip().split("\n")
                    timing_data = {}
                    for line in output_lines:
                        if ":" in line:
                            key, value = line.split(":", 1)
                            timing_data[key] = float(value)

                    times.append(timing_data)
                    print(f"{timing_data.get('TOTAL_TIME', 0):.3f}s")
                else:
                    print(f"ERROR: {result.stderr}")

            except subprocess.TimeoutExpired:
                print("TIMEOUT")
            finally:
                Path(test_file).unlink(missing_ok=True)

        if not times:
            return {"error": "No successful runs"}

        # Calculate statistics
        total_times = [t.get("TOTAL_TIME", 0) for t in times]
        config_times = [t.get("CONFIG_TIME", 0) for t in times]
        import_times = [t.get("IMPORT_TIME", 0) for t in times]
        ready_times = [t.get("READY_TIME", 0) for t in times]

        return {
            "total_time": {
                "mean": statistics.mean(total_times),
                "median": statistics.median(total_times),
                "stdev": statistics.stdev(total_times) if len(total_times) > 1 else 0,
                "min": min(total_times),
                "max": max(total_times),
                "runs": total_times,
            },
            "config_time": {
                "mean": statistics.mean(config_times),
                "median": statistics.median(config_times),
            },
            "import_time": {
                "mean": statistics.mean(import_times),
                "median": statistics.median(import_times),
            },
            "ready_time": {
                "mean": statistics.mean(ready_times),
                "median": statistics.median(ready_times),
            },
        }

    def _analyze_import_performance(self) -> Dict:
        """Analyze import performance using Python's -X importtime."""
        print("  Analyzing import chain with -X importtime...")

        # Create a minimal import test script
        import_script = f"""
import sys
sys.path.insert(0, "{Path.cwd()}")

# Import the key components that trigger all adapter imports
from mcp_the_force.tools import autogen
from mcp_the_force.tools.integration import register_all_tools
from fastmcp import FastMCP

# This should load all adapters
mcp = FastMCP("import-test")
register_all_tools(mcp)
print("Import analysis complete")
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(import_script)
            test_file = f.name

        try:
            # Run with import timing
            result = subprocess.run(
                [sys.executable, "-X", "importtime", test_file],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                return {"error": f"Import analysis failed: {result.stderr}"}

            # Parse import timing from stderr (that's where -X importtime outputs)
            import_data = self._parse_importtime_output(result.stderr)

            return import_data

        except subprocess.TimeoutExpired:
            return {"error": "Import analysis timed out"}
        finally:
            Path(test_file).unlink(missing_ok=True)

    def _parse_importtime_output(self, stderr: str) -> Dict:
        """Parse Python's -X importtime output to extract timing data."""
        lines = stderr.strip().split("\n")
        imports = []

        # Pattern matches: import time: self [us] | cumulative [us] | module name
        pattern = r"import time:\s+(\d+)\s+\|\s+(\d+)\s+\|\s+(.+)"

        for line in lines:
            match = re.match(pattern, line)
            if match:
                self_time = int(match.group(1))
                cumulative_time = int(match.group(2))
                module_name = match.group(3).strip()

                imports.append(
                    {
                        "module": module_name,
                        "self_us": self_time,
                        "cumulative_us": cumulative_time,
                        "self_ms": self_time / 1000.0,
                        "cumulative_ms": cumulative_time / 1000.0,
                    }
                )

        # Sort by cumulative time (heaviest imports first)
        imports.sort(key=lambda x: x["cumulative_us"], reverse=True)

        # Categorize imports
        adapter_imports = [imp for imp in imports if "adapters" in imp["module"]]
        fastmcp_imports = [imp for imp in imports if "fastmcp" in imp["module"]]
        dependency_imports = [
            imp
            for imp in imports
            if any(
                dep in imp["module"]
                for dep in [
                    "openai",
                    "google",
                    "tiktoken",
                    "anthropic",
                    "httpx",
                    "pydantic",
                ]
            )
        ]

        return {
            "total_imports": len(imports),
            "heaviest_imports": imports[:10],  # Top 10 slowest
            "adapter_imports": adapter_imports,
            "fastmcp_imports": fastmcp_imports,
            "dependency_imports": dependency_imports,
            "all_imports": imports if self.detailed_imports else [],
        }

    def _profile_memory_usage(self) -> Dict:
        """Profile memory usage during startup."""
        print("  Profiling memory usage...")

        # Use tracemalloc to measure memory allocations
        memory_script = f"""
import sys
sys.path.insert(0, "{Path.cwd()}")
import tracemalloc
import gc

tracemalloc.start()

# Measure baseline
baseline_current, baseline_peak = tracemalloc.get_traced_memory()

# Import core components
from mcp_the_force.tools import autogen
after_autogen_current, after_autogen_peak = tracemalloc.get_traced_memory()

# Register all tools (triggers adapter imports)
from mcp_the_force.tools.integration import register_all_tools
from fastmcp import FastMCP
mcp = FastMCP("memory-test")
register_all_tools(mcp)
after_register_current, after_register_peak = tracemalloc.get_traced_memory()

# Force garbage collection and get final stats
gc.collect()
final_current, final_peak = tracemalloc.get_traced_memory()

print(f"BASELINE_CURRENT:{{baseline_current}}")
print(f"BASELINE_PEAK:{{baseline_peak}}")
print(f"AUTOGEN_CURRENT:{{after_autogen_current}}")
print(f"AUTOGEN_PEAK:{{after_autogen_peak}}")
print(f"REGISTER_CURRENT:{{after_register_current}}")
print(f"REGISTER_PEAK:{{after_register_peak}}")
print(f"FINAL_CURRENT:{{final_current}}")
print(f"FINAL_PEAK:{{final_peak}}")

tracemalloc.stop()
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(memory_script)
            test_file = f.name

        try:
            result = subprocess.run(
                [sys.executable, test_file], capture_output=True, text=True, timeout=30
            )

            if result.returncode != 0:
                return {"error": f"Memory profiling failed: {result.stderr}"}

            # Parse memory stats
            memory_data = {}
            for line in result.stdout.strip().split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    memory_data[key] = int(value)

            # Convert to MB and calculate deltas
            def bytes_to_mb(bytes_val):
                return bytes_val / (1024 * 1024)

            return {
                "baseline_mb": bytes_to_mb(memory_data.get("BASELINE_CURRENT", 0)),
                "autogen_mb": bytes_to_mb(memory_data.get("AUTOGEN_CURRENT", 0)),
                "register_mb": bytes_to_mb(memory_data.get("REGISTER_CURRENT", 0)),
                "final_mb": bytes_to_mb(memory_data.get("FINAL_CURRENT", 0)),
                "peak_mb": bytes_to_mb(memory_data.get("REGISTER_PEAK", 0)),
                "autogen_delta_mb": bytes_to_mb(
                    memory_data.get("AUTOGEN_CURRENT", 0)
                    - memory_data.get("BASELINE_CURRENT", 0)
                ),
                "register_delta_mb": bytes_to_mb(
                    memory_data.get("REGISTER_CURRENT", 0)
                    - memory_data.get("AUTOGEN_CURRENT", 0)
                ),
            }

        except subprocess.TimeoutExpired:
            return {"error": "Memory profiling timed out"}
        finally:
            Path(test_file).unlink(missing_ok=True)

    def _identify_bottlenecks(self, import_analysis: Dict) -> List[Dict]:
        """Identify the top 3 performance bottlenecks."""
        bottlenecks = []

        if "error" in import_analysis:
            return [{"error": "Could not analyze imports due to error"}]

        # Analyze heaviest imports
        heaviest = import_analysis.get("heaviest_imports", [])
        adapter_imports = import_analysis.get("adapter_imports", [])
        dependency_imports = import_analysis.get("dependency_imports", [])

        # Bottleneck 1: Adapter import chain
        adapter_total_ms = sum(imp["self_ms"] for imp in adapter_imports)
        if adapter_total_ms > 100:  # More than 100ms
            bottlenecks.append(
                {
                    "rank": 1,
                    "category": "Adapter Import Chain",
                    "impact_ms": adapter_total_ms,
                    "description": f"Eager loading of all {len(adapter_imports)} adapters at startup",
                    "modules": [imp["module"] for imp in adapter_imports[:5]],
                    "optimization": "Implement lazy loading with adapter proxy pattern",
                }
            )

        # Bottleneck 2: Heavy dependency imports
        dependency_total_ms = sum(imp["self_ms"] for imp in dependency_imports)
        if dependency_total_ms > 50:  # More than 50ms
            bottlenecks.append(
                {
                    "rank": 2,
                    "category": "Heavy Dependencies",
                    "impact_ms": dependency_total_ms,
                    "description": "Loading heavy ML/API dependencies",
                    "modules": [imp["module"] for imp in dependency_imports[:5]],
                    "optimization": "Defer import of heavy dependencies until first use",
                }
            )

        # Bottleneck 3: Find the single heaviest import
        if heaviest and heaviest[0]["cumulative_ms"] > 50:
            bottlenecks.append(
                {
                    "rank": 3,
                    "category": "Single Heavy Import",
                    "impact_ms": heaviest[0]["cumulative_ms"],
                    "description": f"Heavy import chain in {heaviest[0]['module']}",
                    "modules": [heaviest[0]["module"]],
                    "optimization": "Analyze and optimize this specific import chain",
                }
            )

        # Sort by impact
        bottlenecks.sort(key=lambda x: x["impact_ms"], reverse=True)

        # Re-rank after sorting
        for i, bottleneck in enumerate(bottlenecks[:3]):
            bottleneck["rank"] = i + 1

        return bottlenecks[:3]

    def _generate_recommendations(self, bottlenecks: List[Dict]) -> List[str]:
        """Generate optimization recommendations based on bottlenecks."""
        recommendations = []

        for bottleneck in bottlenecks:
            if bottleneck.get("category") == "Adapter Import Chain":
                recommendations.extend(
                    [
                        "🚀 CRITICAL: Implement lazy adapter loading",
                        "   - Replace eager imports in tools/autogen.py with proxy pattern",
                        "   - Only import adapters when first tool is used",
                        f"   - Expected improvement: {bottleneck.get('impact_ms', 0):.0f}ms → ~10ms",
                    ]
                )
            elif bottleneck.get("category") == "Heavy Dependencies":
                recommendations.extend(
                    [
                        "⚡ HIGH: Defer heavy dependency imports",
                        "   - Move OpenAI/Google SDK imports inside functions",
                        "   - Use import guards for optional dependencies",
                        f"   - Expected improvement: {bottleneck.get('impact_ms', 0):.0f}ms → ~20ms",
                    ]
                )
            elif bottleneck.get("category") == "Single Heavy Import":
                modules = bottleneck.get("modules", ["unknown"])
                recommendations.extend(
                    [
                        f"🔍 INVESTIGATE: Optimize {modules[0] if modules else 'unknown module'}",
                        "   - Profile this specific module's import chain",
                        "   - Look for unnecessary initialization at import time",
                        f"   - Expected improvement: {bottleneck.get('impact_ms', 0):.0f}ms → ~25ms",
                    ]
                )

        # Add general recommendations if no bottlenecks found or on error
        if not bottlenecks or any("error" in str(b) for b in bottlenecks):
            recommendations.extend(
                [
                    "⚠️  Unable to analyze detailed bottlenecks, but general optimizations apply:",
                    "",
                ]
            )

        recommendations.extend(
            [
                "",
                "📋 GENERAL OPTIMIZATIONS:",
                "   - Move Ollama initialization to background task",
                "   - Implement conditional adapter loading based on config",
                "   - Cache tool registration results",
                "   - Use import-time feature flags",
            ]
        )

        return recommendations

    def _print_summary(self):
        """Print a comprehensive summary of the benchmark results."""
        print("\n" + "=" * 60)
        print("📊 BENCHMARK RESULTS SUMMARY")
        print("=" * 60)

        # Startup time summary
        startup = self.results.get("startup_times", {})
        if "error" not in startup:
            total_time = startup.get("total_time", {})
            print("\n⏱️  STARTUP PERFORMANCE:")
            print(
                f"   Total time:    {total_time.get('mean', 0):.3f}s ± {total_time.get('stdev', 0):.3f}s"
            )
            print(
                f"   Range:         {total_time.get('min', 0):.3f}s - {total_time.get('max', 0):.3f}s"
            )
            print(
                f"   Config setup:  {startup.get('config_time', {}).get('mean', 0):.3f}s"
            )
            print(
                f"   Import time:   {startup.get('import_time', {}).get('mean', 0):.3f}s"
            )
            print(
                f"   Ready time:    {startup.get('ready_time', {}).get('mean', 0):.3f}s"
            )

        # Memory usage
        memory = self.results.get("memory_profile", {})
        if "error" not in memory:
            print("\n💾 MEMORY USAGE:")
            print(f"   Baseline:      {memory.get('baseline_mb', 0):.1f} MB")
            print(f"   After autogen: +{memory.get('autogen_delta_mb', 0):.1f} MB")
            print(f"   After register:+{memory.get('register_delta_mb', 0):.1f} MB")
            print(f"   Final usage:   {memory.get('final_mb', 0):.1f} MB")
            print(f"   Peak usage:    {memory.get('peak_mb', 0):.1f} MB")

        # Top bottlenecks
        bottlenecks = self.results.get("bottlenecks", [])
        if bottlenecks and "error" not in bottlenecks[0]:
            print(f"\n🎯 TOP {len(bottlenecks)} PERFORMANCE BOTTLENECKS:")
            for bottleneck in bottlenecks:
                print(
                    f"   #{bottleneck['rank']}. {bottleneck['category']}: {bottleneck['impact_ms']:.1f}ms"
                )
                print(f"       {bottleneck['description']}")

        # Recommendations
        recommendations = self.results.get("recommendations", [])
        if recommendations:
            print("\n💡 OPTIMIZATION RECOMMENDATIONS:")
            for rec in recommendations:
                print(f"   {rec}")

        # Export detailed results
        results_file = Path.cwd() / "benchmark_results.json"
        with open(results_file, "w") as f:
            json.dump(self.results, f, indent=2)
        print(f"\n📄 Detailed results saved to: {results_file}")


def main():
    """Main entry point for the benchmarking script."""
    parser = argparse.ArgumentParser(
        description="Benchmark MCP The-Force server startup performance"
    )
    parser.add_argument(
        "--runs", type=int, default=3, help="Number of benchmark runs (default: 3)"
    )
    parser.add_argument(
        "--detailed-imports",
        action="store_true",
        help="Include detailed import analysis in results",
    )

    args = parser.parse_args()

    benchmark = StartupBenchmark(runs=args.runs, detailed_imports=args.detailed_imports)
    benchmark.run_full_benchmark()


if __name__ == "__main__":
    main()
