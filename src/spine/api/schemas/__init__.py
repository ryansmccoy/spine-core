"""API schemas package.

Manifesto:
    Pydantic schemas define the API contract.  Centralising them
    here keeps routers and ops decoupled from serialisation details.

Tags:
    spine-core, api, schemas, pydantic, contract, serialisation

Doc-Types:
    api-reference
"""

from spine.api.schemas.common import (
    ErrorDetail,
    Link,
    PagedResponse,
    PageMeta,
    ProblemDetail,
    SuccessResponse,
)

__all__ = [
    "ErrorDetail",
    "Link",
    "PageMeta",
    "PagedResponse",
    "ProblemDetail",
    "SuccessResponse",
]
