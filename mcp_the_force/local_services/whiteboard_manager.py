"""WhiteboardManager - Vector store backend for multi-model collaborations."""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import os

from ..vectorstores.manager import VectorStoreManager  
from ..vectorstores.protocol import VSFile
from ..unified_session_cache import UnifiedSessionCache
from ..types.collaboration import CollaborationMessage

logger = logging.getLogger(__name__)


class WhiteboardManager:
    """Manages vector stores for multi-model collaboration whiteboards."""
    
    def __init__(self, 
                 vector_store_manager: Optional[VectorStoreManager] = None,
                 session_cache: Optional[UnifiedSessionCache] = None):
        """Initialize WhiteboardManager with dependencies.
        
        Args:
            vector_store_manager: Vector store manager instance (optional, will use global)
            session_cache: Session cache instance (optional, will use global) 
        """
        # Use dependency injection for testing, but default to global instances
        if vector_store_manager is None:
            from ..vectorstores.manager import vector_store_manager as global_vs_manager
            self.vs_manager = global_vs_manager
        else:
            self.vs_manager = vector_store_manager
            
        if session_cache is None:
            from ..unified_session_cache import unified_session_cache as global_cache
            self.session_cache = global_cache
        else:
            self.session_cache = session_cache

    async def create_whiteboard(self, session_id: str) -> Dict[str, str]:
        """Create dedicated vector store for collaboration.
        
        Tries OpenAI first (enables native file_search), falls back to HNSW.
        
        Args:
            session_id: Collaboration session ID
            
        Returns:
            Dict with store_id and provider
        """
        collab_session_id = f"collab_{session_id}"
        
        # Try OpenAI first
        try:
            logger.debug(f"Creating whiteboard with OpenAI provider for session {session_id}")
            result = await self.vs_manager.create(
                files=[],  # Empty initially
                session_id=collab_session_id,
                provider="openai"
            )
            
            # Use provider from result if available, otherwise default to "openai"
            provider = result.get("provider", "openai")
            store_info = {"store_id": result["store_id"], "provider": provider}
            logger.info(f"Created {provider} whiteboard store {result['store_id']} for session {session_id}")
            
        except Exception as e:
            logger.warning(f"OpenAI whiteboard creation failed for {session_id}: {e}")
            
            # Fallback to HNSW
            try:
                logger.debug(f"Falling back to HNSW provider for session {session_id}")
                result = await self.vs_manager.create(
                    files=[],
                    session_id=collab_session_id,
                    provider="hnsw"
                )
                
                # Use provider from result if available, otherwise default to "hnsw"
                provider = result.get("provider", "hnsw")
                store_info = {"store_id": result["store_id"], "provider": provider}
                logger.info(f"Created {provider} whiteboard store {result['store_id']} for session {session_id}")
                
            except Exception as hnsw_error:
                logger.error(f"Both OpenAI and HNSW whiteboard creation failed for {session_id}: {hnsw_error}")
                raise
        
        # Store metadata for future retrieval
        from ..config import get_settings
        settings = get_settings()
        project = Path(settings.logging.project_path or os.getcwd()).name
        
        await self.session_cache.set_metadata(
            project,
            "chatter_collaborate",
            session_id,
            "whiteboard",
            store_info
        )
        
        return store_info

    async def get_store_info(self, session_id: str) -> Optional[Dict[str, str]]:
        """Get existing whiteboard store info from session metadata.
        
        Args:
            session_id: Collaboration session ID
            
        Returns:
            Dict with store_id and provider, or None if not found
        """
        from ..config import get_settings
        settings = get_settings()
        project = Path(settings.logging.project_path or os.getcwd()).name
        
        return await self.session_cache.get_metadata(
            project,
            "chatter_collaborate",
            session_id, 
            "whiteboard"
        )

    async def get_or_create_store(self, session_id: str) -> Dict[str, str]:
        """Get existing store info or create new whiteboard.
        
        Args:
            session_id: Collaboration session ID
            
        Returns:
            Dict with store_id and provider
        """
        store_info = await self.get_store_info(session_id)
        if store_info:
            logger.debug(f"Reusing existing whiteboard {store_info['store_id']} for session {session_id}")
            return store_info
        
        logger.debug(f"Creating new whiteboard for session {session_id}")
        return await self.create_whiteboard(session_id)

    async def append_message(self, session_id: str, message: CollaborationMessage) -> None:
        """Add message as VSFile to whiteboard.
        
        VSFile path format: whiteboard/{session_id}/{idx:04d}_{speaker}.txt
        
        Args:
            session_id: Collaboration session ID
            message: Message to append
        """
        # Get store info
        store_info = await self.get_store_info(session_id)
        if not store_info:
            raise ValueError(f"No whiteboard store found for session {session_id}")
        
        # Renew lease for long-running collaborations
        await self.vs_manager.renew_lease(f"collab_{session_id}")
        
        # Get next message index using atomic counter for restart safety
        from ..config import get_settings
        settings = get_settings()
        project = Path(settings.logging.project_path or os.getcwd()).name
        
        # Get and increment atomic counter in metadata
        current_seq = await self.session_cache.get_metadata(
            project, "chatter_collaborate", session_id, "whiteboard_seq"
        )
        
        if current_seq is None:
            # Initialize counter
            message_idx = 1
        else:
            # Increment counter
            message_idx = current_seq + 1
        
        # Update counter atomically before using it
        await self.session_cache.set_metadata(
            project, "chatter_collaborate", session_id, "whiteboard_seq", message_idx
        )
        
        # Create VSFile with proper path and metadata
        vsfile_path = f"whiteboard/{session_id}/{message_idx:04d}_{message.speaker}.txt"
        
        # Apply secret redaction before storing
        from ..utils.redaction import redact_secrets
        redacted_content = redact_secrets(message.content)
        
        # Build VSFile content with message and metadata
        content_lines = [
            f"Speaker: {message.speaker}",
            f"Timestamp: {message.timestamp.isoformat()}",
            "",
            redacted_content
        ]
        
        # Add metadata as YAML-style header if present
        if message.metadata:
            content_lines.insert(2, "Metadata:")
            for key, value in message.metadata.items():
                content_lines.insert(3, f"  {key}: {value}")
            content_lines.insert(3 + len(message.metadata), "")
        
        vsfile_content = "\n".join(content_lines)
        
        # Prepare VSFile metadata
        vsfile_metadata = {
            "speaker": message.speaker,
            "timestamp": message.timestamp.isoformat(),
            "session_id": session_id,
            "message_index": message_idx
        }
        # Merge in message metadata
        vsfile_metadata.update(message.metadata)
        
        vsfile = VSFile(
            path=vsfile_path,
            content=vsfile_content,
            metadata=vsfile_metadata
        )
        
        # Add to vector store using correct API
        provider = store_info.get("provider", "openai")
        client = self.vs_manager._get_client_for_store(provider)
        store = await client.get(store_info["store_id"])
        await store.add_files([vsfile])
        
        logger.debug(f"Appended message {message_idx} from {message.speaker} to whiteboard {store_info['store_id']}")

    async def summarize_and_rollover(self, session_id: str, threshold: int) -> None:
        """Summarize old messages and create new store (HNSW can't delete files).
        
        Args:
            session_id: Collaboration session ID
            threshold: Message count threshold for summarization
        """
        # Get current session to check message count
        from ..config import get_settings
        settings = get_settings()
        project = Path(settings.logging.project_path or os.getcwd()).name
        
        collab_state = await self.session_cache.get_metadata(
            project, "chatter_collaborate", session_id, "collab_state"
        )
        
        if not collab_state or len(collab_state.get("messages", [])) < threshold:
            logger.debug(f"Session {session_id} under threshold ({len(collab_state.get('messages', [])) if collab_state else 0} < {threshold}), skipping rollover")
            return
        
        logger.info(f"Starting summarization and rollover for session {session_id} ({len(collab_state.get('messages', []))} messages)")
        
        # Get current store info
        old_store_info = await self.get_store_info(session_id)
        if not old_store_info:
            logger.warning(f"No store info found for session {session_id} rollover")
            return
        
        try:
            # Summarize conversation using describe_session
            from ..local_services.describe_session import DescribeSessionService
            summarizer = DescribeSessionService()
            summary = await summarizer.execute(session_id=session_id)
            
            # Create new store with same provider as old
            old_provider = old_store_info.get("provider", "openai")
            collab_session_id = f"collab_{session_id}_rollover"
            
            # Create with explicit provider
            result = await self.vs_manager.create(
                files=[],
                session_id=collab_session_id,
                provider=old_provider
            )
            new_store_info = {"store_id": result["store_id"], "provider": old_provider}
            
            # Create summary VSFile in new store
            summary_vsfile = VSFile(
                path=f"whiteboard/{session_id}/summary_rollover.md",
                content=f"# Collaboration Summary\n\nRolled over at {datetime.now().isoformat()}\n\n{summary}",
                metadata={"type": "summary", "rollover_timestamp": datetime.now().isoformat()}
            )
            
            # Add summary to new store using correct API
            client = self.vs_manager._get_client_for_store(new_store_info["provider"])
            new_store = await client.get(new_store_info["store_id"])
            await new_store.add_files([summary_vsfile])
            
            # Mark old store inactive (HNSW can't delete files)
            await self.vs_manager.vector_store_cache.set_inactive(old_store_info["store_id"])
            
            # Update session metadata to point to new store
            await self.session_cache.set_metadata(
                project,
                "chatter_collaborate",
                session_id,
                "whiteboard",
                new_store_info
            )
            
            # Reset atomic counter for new store (summary is message 1)
            await self.session_cache.set_metadata(
                project, "chatter_collaborate", session_id, "whiteboard_seq", 1
            )
            
            logger.info(f"Completed rollover for session {session_id}: {old_store_info['store_id']} -> {new_store_info['store_id']}")
            
        except Exception as e:
            logger.error(f"Rollover failed for session {session_id}: {e}")
            raise