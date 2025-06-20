"""Session cache for OpenAI response ID management."""
import time
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class SessionCache:
    """Minimal ephemeral cache for OpenAI response IDs."""
    def __init__(self, ttl=3600):
        self._data = {}
        self.ttl = ttl
    
    def get_response_id(self, session_id: str) -> Optional[str]:
        """Get the previous response ID for a session."""
        self._gc()
        session = self._data.get(session_id)
        if session and time.time() - session['updated'] < self.ttl:
            return session.get('response_id')
        return None
    
    def set_response_id(self, session_id: str, response_id: str):
        """Store a response ID for a session."""
        self._data[session_id] = {
            'response_id': response_id,
            'updated': time.time()
        }
        logger.debug(f"Stored response_id for session {session_id}")
    
    def _gc(self):
        """Garbage collect expired sessions."""
        now = time.time()
        expired = []
        for sid, data in self._data.items():
            if now - data['updated'] >= self.ttl:
                expired.append(sid)
        
        for sid in expired:
            del self._data[sid]
            logger.debug(f"Expired session {sid}")

# Global session cache instance
session_cache = SessionCache()