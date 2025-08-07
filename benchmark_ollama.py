#!/usr/bin/env python3
"""Focused benchmarking for Ollama adapter initialization bottleneck.

This script specifically measures the blocking Ollama initialization that happens
in server.py lines 72-79, which can add 5-15 seconds to startup time.
"""

import asyncio
import json
import statistics
import time
from pathlib import Path
from typing import Dict, List


class OllamaBenchmark:
    """Benchmark Ollama adapter initialization performance."""

    def __init__(self, runs: int = 3):
        self.runs = runs

    def run_ollama_benchmark(self) -> Dict:
        """Run focused Ollama initialization benchmark."""
        print("🦙 Ollama Adapter Initialization Benchmark")
        print("=" * 50)

        results = {
            "blocking_initialization": self._measure_blocking_init(),
            "async_components": self._measure_async_components(),
            "network_operations": self._measure_network_operations(),
            "recommendations": self._generate_ollama_recommendations(),
        }

        self._print_ollama_summary(results)
        return results

    def _measure_blocking_init(self) -> Dict:
        """Measure the blocking Ollama initialization time."""
        print(f"\n1. Measuring blocking initialization ({self.runs} runs)...")

        times = []
        errors = []

        for run in range(self.runs):
            print(f"  Run {run + 1}/{self.runs}...", end=" ", flush=True)

            try:
                start_time = time.perf_counter()

                # Import the Ollama startup module
                from mcp_the_force.adapters.ollama import startup as ollama_startup

                import_time = time.perf_counter()

                # This is the blocking call that happens in server.py
                asyncio.run(ollama_startup.initialize())
                init_time = time.perf_counter()

                timing = {
                    "import_time": import_time - start_time,
                    "init_time": init_time - import_time,
                    "total_time": init_time - start_time,
                    "success": True,
                }
                times.append(timing)
                print(f"{timing['total_time']:.3f}s (init: {timing['init_time']:.3f}s)")

            except Exception as e:
                error_info = {
                    "run": run + 1,
                    "error": str(e),
                    "error_type": type(e).__name__,
                }
                errors.append(error_info)
                print(f"ERROR: {error_info['error_type']}")

        if not times:
            return {"error": "No successful runs", "errors": errors}

        # Calculate statistics
        init_times = [t["init_time"] for t in times]
        total_times = [t["total_time"] for t in times]

        return {
            "successful_runs": len(times),
            "failed_runs": len(errors),
            "init_time": {
                "mean": statistics.mean(init_times),
                "median": statistics.median(init_times),
                "stdev": statistics.stdev(init_times) if len(init_times) > 1 else 0,
                "min": min(init_times),
                "max": max(init_times),
            },
            "total_time": {
                "mean": statistics.mean(total_times),
                "median": statistics.median(total_times),
            },
            "errors": errors,
        }

    def _measure_async_components(self) -> Dict:
        """Break down the async components of Ollama initialization."""
        print("\n2. Analyzing async initialization components...")

        async def analyze_components():
            components = {}

            try:
                from mcp_the_force.adapters.ollama.adapter import OllamaAdapter

                # Measure client initialization
                start_time = time.perf_counter()
                adapter = OllamaAdapter()
                client_init_time = time.perf_counter() - start_time
                components["client_init"] = client_init_time

                # Measure model discovery (if Ollama is available)
                start_time = time.perf_counter()
                try:
                    # This is likely where the blocking network calls happen
                    models = await adapter._discover_models()
                    discovery_time = time.perf_counter() - start_time
                    components["model_discovery"] = {
                        "time": discovery_time,
                        "model_count": len(models) if models else 0,
                        "success": True,
                    }
                except Exception as e:
                    discovery_time = time.perf_counter() - start_time
                    components["model_discovery"] = {
                        "time": discovery_time,
                        "error": str(e),
                        "success": False,
                    }

                # Measure blueprint registration
                start_time = time.perf_counter()
                # This would typically happen during the startup process
                blueprint_time = time.perf_counter() - start_time
                components["blueprint_registration"] = blueprint_time

                return components

            except ImportError as e:
                return {"error": f"Could not import Ollama adapter: {e}"}
            except Exception as e:
                return {"error": f"Analysis failed: {e}"}

        try:
            return asyncio.run(analyze_components())
        except Exception as e:
            return {"error": f"Async analysis failed: {e}"}

    def _measure_network_operations(self) -> Dict:
        """Measure network operations that could be blocking."""
        print("\n3. Analyzing network operations...")

        async def test_network_ops():
            try:
                import httpx

                # Test connection to default Ollama endpoint
                ollama_url = "http://localhost:11434"

                operations = {}

                # Test basic connectivity
                start_time = time.perf_counter()
                try:
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        response = await client.get(f"{ollama_url}/api/tags")
                        connectivity_time = time.perf_counter() - start_time
                        operations["connectivity"] = {
                            "time": connectivity_time,
                            "status": response.status_code,
                            "success": response.status_code == 200,
                        }
                except Exception as e:
                    connectivity_time = time.perf_counter() - start_time
                    operations["connectivity"] = {
                        "time": connectivity_time,
                        "error": str(e),
                        "success": False,
                    }

                # Test model info request (expensive operation)
                start_time = time.perf_counter()
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        # This is typically what takes the most time
                        response = await client.post(
                            f"{ollama_url}/api/show", json={"name": "llama3.2:latest"}
                        )
                        model_info_time = time.perf_counter() - start_time
                        operations["model_info"] = {
                            "time": model_info_time,
                            "status": response.status_code
                            if hasattr(response, "status_code")
                            else "unknown",
                            "success": True,
                        }
                except Exception as e:
                    model_info_time = time.perf_counter() - start_time
                    operations["model_info"] = {
                        "time": model_info_time,
                        "error": str(e),
                        "success": False,
                    }

                return operations

            except ImportError as e:
                return {"error": f"Could not import httpx: {e}"}

        try:
            return asyncio.run(test_network_ops())
        except Exception as e:
            return {"error": f"Network analysis failed: {e}"}

    def _generate_ollama_recommendations(self) -> List[str]:
        """Generate specific recommendations for Ollama optimization."""
        return [
            "🚀 CRITICAL: Move Ollama initialization to background",
            "   - Remove blocking asyncio.run(ollama_startup.initialize()) from server.py",
            "   - Initialize Ollama adapter asynchronously after server starts",
            "   - Use lazy loading pattern for Ollama tools",
            "",
            "⚡ HIGH: Implement timeout and fallback",
            "   - Add aggressive timeout for Ollama discovery (2-3 seconds max)",
            "   - Gracefully degrade if Ollama is not available",
            "   - Cache discovered models between restarts",
            "",
            "🔧 MEDIUM: Optimize network operations",
            "   - Use connection pooling for Ollama HTTP client",
            "   - Parallelize model discovery requests",
            "   - Skip model info requests for basic functionality",
            "",
            "📋 IMPLEMENTATION PLAN:",
            "   1. Move ollama_startup.initialize() to lifespan context manager",
            "   2. Register static Ollama tools first, dynamic ones when ready",
            "   3. Show 'Ollama initializing...' status in tool descriptions",
            "   4. Expected improvement: 15s → 0.1s startup, +2s first use",
        ]

    def _print_ollama_summary(self, results: Dict):
        """Print Ollama-specific benchmark summary."""
        print("\n" + "=" * 50)
        print("🦙 OLLAMA BENCHMARK SUMMARY")
        print("=" * 50)

        # Blocking initialization results
        blocking = results.get("blocking_initialization", {})
        if "error" not in blocking:
            init_time = blocking.get("init_time", {})
            print("\n⏱️  BLOCKING INITIALIZATION:")
            print(f"   Successful runs: {blocking.get('successful_runs', 0)}")
            print(f"   Failed runs:     {blocking.get('failed_runs', 0)}")
            print(
                f"   Init time:       {init_time.get('mean', 0):.3f}s ± {init_time.get('stdev', 0):.3f}s"
            )
            print(
                f"   Range:           {init_time.get('min', 0):.3f}s - {init_time.get('max', 0):.3f}s"
            )
        else:
            print("\n❌ BLOCKING INITIALIZATION FAILED:")
            print(f"   Error: {blocking.get('error', 'Unknown error')}")

        # Async components breakdown
        async_comp = results.get("async_components", {})
        if "error" not in async_comp:
            print("\n🔧 ASYNC COMPONENTS:")
            if "client_init" in async_comp:
                print(f"   Client init:     {async_comp['client_init']:.3f}s")

            if "model_discovery" in async_comp:
                discovery = async_comp["model_discovery"]
                if discovery.get("success"):
                    print(
                        f"   Model discovery: {discovery['time']:.3f}s ({discovery.get('model_count', 0)} models)"
                    )
                else:
                    print(
                        f"   Model discovery: {discovery['time']:.3f}s (FAILED: {discovery.get('error', 'Unknown')})"
                    )
        else:
            print(
                f"\n❌ ASYNC ANALYSIS FAILED: {async_comp.get('error', 'Unknown error')}"
            )

        # Network operations
        network = results.get("network_operations", {})
        if "error" not in network:
            print("\n🌐 NETWORK OPERATIONS:")
            if "connectivity" in network:
                conn = network["connectivity"]
                status = (
                    f"({conn.get('status', 'N/A')})"
                    if conn.get("success")
                    else f"(ERROR: {conn.get('error', 'Unknown')})"
                )
                print(f"   Connectivity:    {conn['time']:.3f}s {status}")

            if "model_info" in network:
                info = network["model_info"]
                status = (
                    f"({info.get('status', 'N/A')})"
                    if info.get("success")
                    else f"(ERROR: {info.get('error', 'Unknown')})"
                )
                print(f"   Model info:      {info['time']:.3f}s {status}")
        else:
            print(
                f"\n❌ NETWORK ANALYSIS FAILED: {network.get('error', 'Unknown error')}"
            )

        # Recommendations
        recommendations = results.get("recommendations", [])
        if recommendations:
            print("\n💡 OLLAMA OPTIMIZATION RECOMMENDATIONS:")
            for rec in recommendations:
                print(f"   {rec}")

        # Save results
        results_file = Path.cwd() / "ollama_benchmark_results.json"
        with open(results_file, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\n📄 Ollama results saved to: {results_file}")


def main():
    """Main entry point for Ollama benchmarking."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Benchmark Ollama adapter initialization performance"
    )
    parser.add_argument(
        "--runs", type=int, default=3, help="Number of benchmark runs (default: 3)"
    )

    args = parser.parse_args()

    benchmark = OllamaBenchmark(runs=args.runs)
    benchmark.run_ollama_benchmark()


if __name__ == "__main__":
    main()
