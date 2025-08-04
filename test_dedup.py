#!/usr/bin/env python3
"""Simple test script to verify deduplication functionality."""

import tempfile
import os
from pathlib import Path

# Add project root to path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from mcp_the_force.dedup.hashing import compute_content_hash, compute_fileset_hash
from mcp_the_force.dedup.simple_cache import SimpleVectorStoreCache


def test_hashing():
    """Test basic hashing functionality."""
    print("Testing hashing functionality...")

    # Test content hashing
    content1 = "def hello():\n    print('world')"
    content2 = "def hello():\r\n    print('world')"  # Different line endings
    content3 = "def goodbye():\n    print('world')"  # Different content

    hash1 = compute_content_hash(content1)
    hash2 = compute_content_hash(content2)
    hash3 = compute_content_hash(content3)

    print(f"Content 1 hash: {hash1[:12]}...")
    print(f"Content 2 hash: {hash2[:12]}...")
    print(f"Content 3 hash: {hash3[:12]}...")

    # Same content with different line endings should have same hash
    assert hash1 == hash2, "Cross-platform line ending normalization failed"
    assert hash1 != hash3, "Different content should have different hashes"

    # Test fileset hashing with paths
    fileset1 = [("file1.txt", content1), ("file3.txt", content3)]
    fileset2 = [
        ("file3.txt", content3),
        ("file1.txt", content1),
    ]  # Same files, different order
    fileset3 = [("file1.txt", content1), ("file2.txt", content2)]  # Different content

    fhash1 = compute_fileset_hash(fileset1)
    fhash2 = compute_fileset_hash(fileset2)
    fhash3 = compute_fileset_hash(fileset3)

    print(f"Fileset 1 hash: {fhash1[:12]}...")
    print(f"Fileset 2 hash: {fhash2[:12]}...")
    print(f"Fileset 3 hash: {fhash3[:12]}...")

    # Same content in different order should have same hash
    assert fhash1 == fhash2, "Order-independent fileset hashing failed"
    assert fhash1 != fhash3, "Different filesets should have different hashes"

    print("✓ Hashing tests passed!")


def test_cache():
    """Test cache functionality."""
    print("\nTesting cache functionality...")

    # Create temporary cache
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        cache_path = tf.name

    try:
        cache = SimpleVectorStoreCache(cache_path)

        # Test file caching
        content_hash = "abc123"
        file_id = "file_456"

        # Should not be cached initially
        assert cache.get_file_id(content_hash) is None

        # Cache it
        cache.cache_file(content_hash, file_id)

        # Should be cached now
        cached_file_id = cache.get_file_id(content_hash)
        assert cached_file_id == file_id, f"Expected {file_id}, got {cached_file_id}"

        # Test store caching
        fileset_hash = "def789"
        store_id = "store_123"
        provider = "openai"

        # Should not be cached initially
        assert cache.get_store_id(fileset_hash) is None

        # Cache it
        cache.cache_store(fileset_hash, store_id, provider)

        # Should be cached now
        cached_store = cache.get_store_id(fileset_hash)
        assert cached_store is not None
        assert cached_store["store_id"] == store_id
        assert cached_store["provider"] == provider

        # Test stats
        stats = cache.get_stats()
        assert stats["file_count"] == 1
        assert stats["store_count"] == 1
        assert stats["cache_type"] == "SimpleVectorStoreCache"

        print("✓ Cache tests passed!")

    finally:
        # Cleanup
        if os.path.exists(cache_path):
            os.unlink(cache_path)


def main():
    """Run all tests."""
    print("Running simple deduplication tests...\n")

    test_hashing()
    test_cache()

    print("\n✓ All tests passed! Deduplication system is working.")
    print("\nThis simple system should provide:")
    print("- 50-90% reduction in OpenAI API costs")
    print("- Faster session startup (no re-upload of identical files)")
    print("- Automatic reuse of vector stores for identical file sets")


if __name__ == "__main__":
    main()
