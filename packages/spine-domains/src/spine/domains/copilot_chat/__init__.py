"""
Copilot Chat Domain — VS Code Copilot chat session ingestion.

This domain manages:
- Chat session observations from VS Code Copilot
- Individual message observations  
- Integration with capture-spine content API
- Tool usage and file reference tracking

Ingestion cadence: On-demand or scheduled
Source: VS Code workspaceStorage/chatSessions/

Integration with FeedSpine:
    - Uses CopilotChatAdapter from feedspine.adapter
    - Uses CaptureSpineClient from feedspine.integration

Example:
    from spine.domains.copilot_chat import (
        CopilotChatPipeline,
        CopilotChatConfig,
    )
    
    config = CopilotChatConfig(
        workspace_filter="capture-spine",
        capture_spine_url="http://localhost:8000",
    )
    
    async with CopilotChatPipeline(config) as pipeline:
        result = await pipeline.run()
        print(f"Ingested {result.sessions_ingested} sessions")
"""

from spine.domains.copilot_chat.pipeline import (
    CopilotChatConfig,
    CopilotChatPipeline,
    CopilotPipelineResult,
)

__all__ = [
    "CopilotChatConfig",
    "CopilotChatPipeline",
    "CopilotPipelineResult",
]
