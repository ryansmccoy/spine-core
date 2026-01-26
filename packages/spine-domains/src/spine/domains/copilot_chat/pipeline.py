"""
Copilot Chat Pipeline — Orchestrates VS Code chat ingestion.

This pipeline:
1. Fetches chat sessions from VS Code storage via FeedSpine adapter
2. Optionally enriches with TODO extraction and summarization
3. Posts to capture-spine Content Ingestion API
4. Tracks all work in spine-core manifest

Example:
    from spine.domains.copilot_chat import CopilotChatPipeline, CopilotChatConfig
    from spine.core import new_context
    
    config = CopilotChatConfig(
        workspace_filter="capture-spine",
        since_days=7,
        capture_spine_url="http://localhost:8000",
    )
    
    async with CopilotChatPipeline(config) as pipeline:
        result = await pipeline.run(ctx=new_context())
        print(f"Ingested {result.sessions_ingested} sessions")
        print(f"Duplicates: {result.duplicates}")
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from feedspine.adapter.copilot_chat import CopilotChatAdapter
    from feedspine.integration.capture_spine import CaptureSpineClient
    from feedspine.models.observation import ChatSessionObservation
    from spine.core import ExecutionContext, WorkManifest


@dataclass
class CopilotChatConfig:
    """Configuration for copilot chat ingestion pipeline.
    
    Attributes:
        workspace_filter: Filter to specific workspace name (partial match)
        since_days: Only fetch sessions from last N days
        include_messages: Also ingest individual messages
        capture_spine_url: URL for capture-spine API
        capture_spine_api_key: Optional API key
        generate_summary: Request LLM summary generation
        extract_todos: Request TODO extraction
        dry_run: Don't actually POST, just collect
    """
    
    # Source filtering
    workspace_filter: str | None = None
    since_days: int | None = None
    include_messages: bool = False
    
    # Capture-spine settings
    capture_spine_url: str = "http://localhost:8000"
    capture_spine_api_key: str | None = None
    
    # Processing options
    generate_summary: bool = True
    extract_todos: bool = True
    extract_entities: bool = True
    
    # Mode
    dry_run: bool = False
    
    @property
    def since_datetime(self) -> datetime | None:
        """Convert since_days to datetime."""
        if self.since_days is None:
            return None
        return datetime.now(UTC) - timedelta(days=self.since_days)


@dataclass
class CopilotPipelineResult:
    """Result of pipeline execution.
    
    Attributes:
        sessions_fetched: Total sessions fetched from VS Code
        sessions_ingested: Sessions successfully sent to capture-spine
        messages_ingested: Messages ingested (if include_messages)
        duplicates: Sessions that were duplicates
        errors: List of error messages
    """
    
    sessions_fetched: int = 0
    sessions_ingested: int = 0
    messages_ingested: int = 0
    duplicates: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)
    
    # Tracking
    batch_id: str = ""
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    
    @property
    def success(self) -> bool:
        return len(self.errors) == 0
    
    @property
    def summary(self) -> dict[str, Any]:
        return {
            "sessions_fetched": self.sessions_fetched,
            "sessions_ingested": self.sessions_ingested,
            "messages_ingested": self.messages_ingested,
            "duplicates": self.duplicates,
            "failed": self.failed,
            "errors": len(self.errors),
            "batch_id": self.batch_id,
            "duration_seconds": (
                (self.completed_at - self.started_at).total_seconds()
                if self.completed_at
                else None
            ),
        }


class CopilotChatPipeline:
    """
    Orchestrates VS Code Copilot chat ingestion to capture-spine.
    
    Stages:
    1. FETCH: Get chat sessions from VS Code storage
    2. ENRICH: (optional) Extract TODOs, summaries
    3. INGEST: POST to capture-spine API
    
    Example:
        config = CopilotChatConfig(
            workspace_filter="my-project",
            since_days=7,
        )
        
        pipeline = CopilotChatPipeline(config)
        await pipeline.initialize()
        
        result = await pipeline.run()
        print(f"Ingested: {result.sessions_ingested}")
    """
    
    def __init__(
        self,
        config: CopilotChatConfig,
        manifest: "WorkManifest | None" = None,
    ):
        self.config = config
        self.manifest = manifest
        self._adapter: "CopilotChatAdapter | None" = None
        self._client: "CaptureSpineClient | None" = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize adapters and clients."""
        # Initialize FeedSpine adapter
        try:
            from feedspine.adapter.copilot_chat import CopilotChatAdapter
            
            self._adapter = CopilotChatAdapter(
                name="copilot-chat-pipeline",
                workspace_filter=self.config.workspace_filter,
                since=self.config.since_datetime,
                include_messages=self.config.include_messages,
            )
            await self._adapter.initialize()
        except ImportError as e:
            raise ImportError(
                "feedspine is required for CopilotChatPipeline. "
                "Install with: pip install feedspine"
            ) from e
        
        # Initialize capture-spine client (unless dry run)
        if not self.config.dry_run:
            try:
                from feedspine.integration.capture_spine import CaptureSpineClient
                
                self._client = CaptureSpineClient(
                    base_url=self.config.capture_spine_url,
                    api_key=self.config.capture_spine_api_key,
                )
            except ImportError:
                # CaptureSpineClient not available - dry run mode
                self._client = None
        
        self._initialized = True
    
    async def close(self) -> None:
        """Clean up resources."""
        if self._adapter:
            await self._adapter.close()
        if self._client:
            await self._client.close()
        self._initialized = False
    
    async def __aenter__(self) -> "CopilotChatPipeline":
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()
    
    async def run(self, ctx: "ExecutionContext | None" = None) -> CopilotPipelineResult:
        """
        Execute the full pipeline.
        
        Args:
            ctx: Execution context for lineage tracking
        
        Returns:
            CopilotPipelineResult with stats
        """
        if not self._initialized:
            await self.initialize()
        
        # Generate batch ID
        batch_id = datetime.now(UTC).strftime("copilot-%Y%m%d-%H%M%S")
        if ctx:
            batch_id = ctx.batch_id or batch_id
        
        result = CopilotPipelineResult(batch_id=batch_id)
        
        try:
            # Stage 1: Fetch sessions from VS Code
            sessions = await self._fetch_sessions(result)
            
            # Stage 2: Post to capture-spine
            if not self.config.dry_run and self._client:
                await self._ingest_sessions(sessions, result)
            else:
                # Dry run - just count
                result.sessions_ingested = len(sessions)
                
        except Exception as e:
            result.errors.append(f"Pipeline error: {e}")
        
        result.completed_at = datetime.now(UTC)
        return result
    
    async def _fetch_sessions(
        self,
        result: CopilotPipelineResult,
    ) -> list["ChatSessionObservation"]:
        """Stage 1: Fetch chat sessions from VS Code storage."""
        from feedspine.models.observation import ChatSessionObservation
        
        sessions: list[ChatSessionObservation] = []
        
        if self._adapter is None:
            result.errors.append("Adapter not initialized")
            return sessions
        
        try:
            async for record in self._adapter.fetch():
                # Filter to just sessions (not messages)
                if "chat_session" in record.metadata.source_type:
                    obs = ChatSessionObservation(**record.content)
                    sessions.append(obs)
                    result.sessions_fetched += 1
                    
        except Exception as e:
            result.errors.append(f"Fetch error: {e}")
        
        return sessions
    
    async def _ingest_sessions(
        self,
        sessions: list["ChatSessionObservation"],
        result: CopilotPipelineResult,
    ) -> None:
        """Stage 2: Post sessions to capture-spine."""
        if self._client is None:
            result.errors.append("Capture-spine client not initialized")
            return
        
        async with self._client:
            for session in sessions:
                try:
                    ingest_result = await self._client.ingest_chat_session(
                        session,
                        generate_summary=self.config.generate_summary,
                        extract_todos=self.config.extract_todos,
                        extract_entities=self.config.extract_entities,
                    )
                    
                    if ingest_result.status == "accepted":
                        result.sessions_ingested += 1
                    elif ingest_result.status == "duplicate":
                        result.duplicates += 1
                    elif ingest_result.status == "updated":
                        result.sessions_ingested += 1
                    elif ingest_result.status == "failed":
                        result.failed += 1
                        if ingest_result.error:
                            result.errors.append(ingest_result.error)
                            
                except Exception as e:
                    result.failed += 1
                    result.errors.append(f"Ingest error for {session.session_id}: {e}")


# Convenience function for CLI usage
async def ingest_copilot_chats(
    workspace_filter: str | None = None,
    since_days: int | None = None,
    capture_spine_url: str = "http://localhost:8000",
    dry_run: bool = False,
) -> CopilotPipelineResult:
    """
    Convenience function to run copilot chat ingestion.
    
    Args:
        workspace_filter: Filter to specific workspace
        since_days: Only sessions from last N days
        capture_spine_url: Capture-spine API URL
        dry_run: Don't actually POST
    
    Returns:
        Pipeline result
    
    Example:
        result = await ingest_copilot_chats(
            workspace_filter="capture-spine",
            since_days=7,
        )
        print(f"Ingested {result.sessions_ingested} sessions")
    """
    config = CopilotChatConfig(
        workspace_filter=workspace_filter,
        since_days=since_days,
        capture_spine_url=capture_spine_url,
        dry_run=dry_run,
    )
    
    async with CopilotChatPipeline(config) as pipeline:
        return await pipeline.run()
