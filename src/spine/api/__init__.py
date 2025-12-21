"""
REST API layer for spine-core.

Provides a FastAPI application factory with typed endpoints that
delegate to the operations layer (``spine.ops``).  All business logic
lives in ops — this package handles only HTTP transport concerns:
serialisation, authentication, error mapping, and request context.

Quick start::

    from spine.api import create_app

    app = create_app()  # ready for uvicorn

Manifesto:
    This package owns the HTTP boundary.  All business logic lives
    in ``spine.ops``; routers here handle only serialisation,
    authentication, error mapping, and request context.

Tags:
    spine-core, api, REST, FastAPI, transport-layer

Doc-Types:
    api-reference
"""

from spine.api.app import create_app

__all__ = ["create_app"]
