"""Unit tests for session cache implementations."""
import os
import tempfile
import time
import threading
import pytest
from unittest.mock import patch

from mcp_second_brain.session_cache import (
    _SQLiteSessionCache,
    _InMemorySessionCache
)


class TestInMemorySessionCache:
    """Test the in-memory session cache implementation."""
    
    def test_basic_set_get(self):
        """Test basic set and get operations."""
        cache = _InMemorySessionCache(ttl=3600)
        
        # Set a session
        cache.set_response_id("session1", "response1")
        
        # Get it back
        assert cache.get_response_id("session1") == "response1"
        
        # Non-existent session
        assert cache.get_response_id("nonexistent") is None
    
    def test_expiration(self):
        """Test TTL expiration."""
        cache = _InMemorySessionCache(ttl=1)  # 1 second TTL
        
        cache.set_response_id("session1", "response1")
        assert cache.get_response_id("session1") == "response1"
        
        # Wait for expiration
        time.sleep(1.1)
        assert cache.get_response_id("session1") is None
    
    def test_update_extends_ttl(self):
        """Test that updating a session extends its TTL."""
        cache = _InMemorySessionCache(ttl=2)
        
        cache.set_response_id("session1", "response1")
        time.sleep(1)
        
        # Update before expiration
        cache.set_response_id("session1", "response2")
        time.sleep(1)
        
        # Should still be valid (total 2 seconds, but updated at 1 second)
        assert cache.get_response_id("session1") == "response2"


class TestSQLiteSessionCache:
    """Test the SQLite session cache implementation."""
    
    @pytest.fixture
    def cache(self):
        """Create a temporary SQLite cache."""
        with tempfile.NamedTemporaryFile(suffix='.sqlite3', delete=False) as f:
            db_path = f.name
        
        cache = _SQLiteSessionCache(db_path=db_path, ttl=3600)
        yield cache
        
        # Cleanup
        cache.close()
        try:
            os.unlink(db_path)
        except Exception:
            pass
    
    def test_basic_set_get(self, cache):
        """Test basic set and get operations."""
        # Set a session
        cache.set_response_id("session1", "response1")
        
        # Get it back
        assert cache.get_response_id("session1") == "response1"
        
        # Non-existent session
        assert cache.get_response_id("nonexistent") is None
    
    def test_persistence(self):
        """Test that data persists across cache instances."""
        with tempfile.NamedTemporaryFile(suffix='.sqlite3', delete=False) as f:
            db_path = f.name
        
        try:
            # First instance
            cache1 = _SQLiteSessionCache(db_path=db_path, ttl=3600)
            cache1.set_response_id("persistent", "value1")
            cache1.close()
            
            # Second instance - should see the data
            cache2 = _SQLiteSessionCache(db_path=db_path, ttl=3600)
            assert cache2.get_response_id("persistent") == "value1"
            cache2.close()
        finally:
            os.unlink(db_path)
    
    def test_expiration(self):
        """Test TTL expiration."""
        with tempfile.NamedTemporaryFile(suffix='.sqlite3', delete=False) as f:
            db_path = f.name
        
        try:
            cache = _SQLiteSessionCache(db_path=db_path, ttl=1)  # 1 second TTL
            
            cache.set_response_id("session1", "response1")
            assert cache.get_response_id("session1") == "response1"
            
            # Wait for expiration
            time.sleep(1.1)
            assert cache.get_response_id("session1") is None
            
            cache.close()
        finally:
            os.unlink(db_path)
    
    def test_concurrent_access(self, cache):
        """Test thread-safe concurrent access."""
        results = []
        errors = []
        
        def worker(worker_id):
            try:
                for i in range(10):
                    session_id = f"worker{worker_id}_session{i}"
                    response_id = f"response{worker_id}_{i}"
                    
                    cache.set_response_id(session_id, response_id)
                    retrieved = cache.get_response_id(session_id)
                    
                    if retrieved != response_id:
                        errors.append(f"Mismatch: {retrieved} != {response_id}")
                    else:
                        results.append(True)
            except Exception as e:
                errors.append(str(e))
        
        # Create multiple threads
        threads = []
        for i in range(5):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()
        
        # Wait for all threads
        for t in threads:
            t.join()
        
        # Check results
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 50  # 5 workers * 10 operations each
    
    def test_probabilistic_cleanup(self, cache):
        """Test that cleanup removes expired sessions."""
        # Override cleanup probability to always trigger
        with patch('mcp_second_brain.session_cache._PURGE_PROB', 1.0):
            # Create a cache with 1 second TTL
            with tempfile.NamedTemporaryFile(suffix='.sqlite3', delete=False) as f:
                db_path = f.name
            
            try:
                cache = _SQLiteSessionCache(db_path=db_path, ttl=1)
                
                # Add some sessions
                cache.set_response_id("old1", "response1")
                cache.set_response_id("old2", "response2")
                
                # Wait for them to expire
                time.sleep(1.1)
                
                # Add a new session - this should trigger cleanup
                cache.set_response_id("new1", "response3")
                
                # Old sessions should be gone
                assert cache.get_response_id("old1") is None
                assert cache.get_response_id("old2") is None
                
                # New session should exist
                assert cache.get_response_id("new1") == "response3"
                
                cache.close()
            finally:
                os.unlink(db_path)
    
    def test_long_ids_rejected(self, cache):
        """Test that overly long IDs are rejected."""
        long_id = "x" * 1025
        
        with pytest.raises(ValueError, match="too long"):
            cache.set_response_id(long_id, "response1")
        
        with pytest.raises(ValueError, match="too long"):
            cache.set_response_id("session1", long_id)
        
        with pytest.raises(ValueError, match="too long"):
            cache.get_response_id(long_id)


class TestSessionCacheFactory:
    """Test the factory pattern and fallback behavior."""
    
    def test_sqlite_fallback_on_error(self):
        """Test fallback to in-memory when SQLite fails."""
        # Force SQLite to fail by using an invalid path
        with patch.dict(os.environ, {'SESSION_DB_PATH': '/dev/null/invalid.db'}):
            # Need to reimport to pick up new env var
            import importlib
            import mcp_second_brain.session_cache
            importlib.reload(mcp_second_brain.session_cache)
            
            # Should have fallen back to in-memory
            cache = mcp_second_brain.session_cache.session_cache
            
            # Should still work
            cache.set_response_id("test", "value")
            assert cache.get_response_id("test") == "value"
    
    def test_proxy_interface(self):
        """Test that SessionCache proxy maintains the interface."""
        # The global session_cache should work
        from mcp_second_brain.session_cache import session_cache
        
        session_cache.set_response_id("proxy_test", "proxy_value")
        assert session_cache.get_response_id("proxy_test") == "proxy_value"
        
        # Close should not raise
        session_cache.close()