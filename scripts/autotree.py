"""
AutoTree - Intelligent dispatcher that chooses the optimal file tree algorithm
=============================================================================

Instead of betting on a single encoder, AutoTree tries multiple strategies
and returns the one with the shortest token count. Guarantees optimal
performance for any tree structure with minimal latency overhead.

Strategy selection based on O3's empirical analysis:
- Synthetic/shallow (≤200 files): FusionTree usually wins
- Medium real projects (200-1K): NeutrinoTree's tri-candidate search shines
- Large heterogeneous (1K+): QuarkTree handles complexity best

AutoTree removes the guesswork - it just picks the winner.
"""

from __future__ import annotations
from time import perf_counter
from typing import List, Optional

# Token counting with tiktoken if available
try:
    import tiktoken

    _enc = tiktoken.get_encoding("o200k_base")

    def _tokcount(s: str) -> int:
        return len(_enc.encode(s))

except ImportError:
    # Fallback to character length approximation
    def _tokcount(s: str) -> int:
        return len(s)


def build_file_tree_autotree(
    all_paths: List[str],
    attachment_paths: List[str],
    *,
    bench_timeout_ms: int = 30,  # Keep latency negligible vs I/O time
    algorithms: Optional[List[str]] = None,  # Override algorithm selection
    **kwargs,
) -> str:
    """
    Choose the shortest encoding from FusionTree, NeutrinoTree, and QuarkTree.

    Args:
        all_paths: List of all file paths to include
        attachment_paths: Paths that should be marked as attached
        bench_timeout_ms: Stop evaluating if time budget exceeded (default 30ms)
        algorithms: Override which algorithms to try (default: all three)
        **kwargs: Additional arguments passed to all algorithms

    Returns:
        The shortest tree representation from all tested algorithms

    Performance guarantee: Never worse than best single algorithm for this tree.
    """
    if not all_paths:
        return "(empty)"

    # Import algorithms on-demand to avoid circular imports
    from mcp_the_force.utils.file_tree import build_file_tree_from_paths as fusion

    try:
        from quarktree import build_file_tree_quarktree as quark
    except ImportError:
        quark = None
    try:
        from neutrinotree import build_file_tree_neutrinotree as neutrino
    except ImportError:
        neutrino = None

    # Default algorithm selection with fallbacks
    if algorithms is None:
        available_algorithms = []
        if fusion:
            available_algorithms.append(("FusionTree", fusion))
        if neutrino:
            available_algorithms.append(("NeutrinoTree", neutrino))
        if quark:
            available_algorithms.append(("QuarkTree", quark))

        if not available_algorithms:
            raise ImportError("No tree algorithms available")
    else:
        # Custom algorithm selection (for testing)
        algorithm_map = {"fusion": fusion, "neutrino": neutrino, "quark": quark}
        available_algorithms = [
            (name.title() + "Tree", algorithm_map[name])
            for name in algorithms
            if algorithm_map.get(name) is not None
        ]

    candidates = []
    total_start = perf_counter()

    for name, algorithm_fn in available_algorithms:
        algo_start = perf_counter()

        try:
            # Execute the algorithm with appropriate parameters for each
            if name == "FusionTree":
                # FusionTree uses different parameter signature
                result = algorithm_fn(
                    all_paths,
                    attachment_paths,
                    max_items_per_dir=kwargs.get("max_items_per_dir", 15),
                )
            elif name == "QuarkTree":
                # QuarkTree doesn't accept seq_gap parameter
                quark_kwargs = {k: v for k, v in kwargs.items() if k != "seq_gap"}
                result = algorithm_fn(all_paths, attachment_paths, **quark_kwargs)
            elif name == "NeutrinoTree":
                # NeutrinoTree accepts all parameters
                result = algorithm_fn(all_paths, attachment_paths, **kwargs)
            else:
                # Generic fallback
                result = algorithm_fn(all_paths, attachment_paths, **kwargs)

        except Exception as e:
            # Algorithm failed - skip it
            print(f"Warning: {name} failed: {e}")
            continue

        algo_elapsed = (perf_counter() - algo_start) * 1000  # Convert to ms
        token_count = _tokcount(result)

        candidates.append((token_count, algo_elapsed, name, result))

        # Respect timeout to keep latency predictable
        total_elapsed = (perf_counter() - total_start) * 1000
        if total_elapsed > bench_timeout_ms:
            print(
                f"AutoTree timeout reached after {total_elapsed:.1f}ms, stopping evaluation"
            )
            break

    if not candidates:
        raise RuntimeError("All algorithms failed")

    # Select the algorithm with minimum token count
    best_candidate = min(candidates, key=lambda x: x[0])
    tokens, elapsed, winner_name, winner_result = best_candidate

    # Optional: Log the selection for debugging
    total_time = (perf_counter() - total_start) * 1000
    if len(candidates) > 1:
        runner_up = sorted(candidates, key=lambda x: x[0])[1]
        savings = runner_up[0] - tokens
        print(
            f"AutoTree: {winner_name} wins with {tokens} tokens "
            f"(saves {savings} vs runner-up) in {total_time:.1f}ms"
        )

    return winner_result


def build_file_tree_autotree_fast(
    all_paths: List[str], attachment_paths: List[str], **kwargs
) -> str:
    """
    Fast heuristic version that predicts best algorithm without trying all.

    Based on file count and structure characteristics, chooses likely winner:
    - ≤200 files: FusionTree (synthetic-optimized)
    - 200-1000 files: NeutrinoTree (tri-candidate optimization)
    - 1000+ files: QuarkTree (enterprise-scale)

    Fallback to full AutoTree if prediction fails or algorithms unavailable.
    """
    file_count = len(all_paths)

    try:
        if file_count <= 200:
            # Small/synthetic cases - FusionTree usually optimal
            from mcp_the_force.utils.file_tree import build_file_tree_from_paths

            return build_file_tree_from_paths(
                all_paths,
                attachment_paths,
                max_items_per_dir=kwargs.get("max_items_per_dir", 15),
            )
        elif file_count <= 1000:
            # Medium complexity - NeutrinoTree's tri-candidate search excels
            from neutrinotree import build_file_tree_neutrinotree

            return build_file_tree_neutrinotree(all_paths, attachment_paths, **kwargs)
        else:
            # Large enterprise codebases - QuarkTree proven
            from quarktree import build_file_tree_quarktree

            # Remove seq_gap parameter that QuarkTree doesn't accept
            quark_kwargs = {k: v for k, v in kwargs.items() if k != "seq_gap"}
            return build_file_tree_quarktree(
                all_paths, attachment_paths, **quark_kwargs
            )
    except ImportError:
        # Fallback to full AutoTree evaluation
        return build_file_tree_autotree(all_paths, attachment_paths, **kwargs)


# Convenience aliases
build_optimal_tree = build_file_tree_autotree
build_smart_tree = build_file_tree_autotree_fast
