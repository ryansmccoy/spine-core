"""Spine framework exceptions."""


class SpineError(Exception):
    """Base exception for all Spine framework errors."""

    pass


class PipelineNotFoundError(SpineError):
    """Raised when a requested pipeline is not registered."""

    def __init__(self, pipeline_name: str):
        self.pipeline_name = pipeline_name
        super().__init__(f"Pipeline not found: {pipeline_name}")


class BadParamsError(SpineError):
    """Raised when pipeline parameters are invalid."""

    def __init__(
        self,
        message: str,
        missing_params: list[str] | None = None,
        invalid_params: list[str] | None = None,
    ):
        self.missing_params = missing_params or []
        self.invalid_params = invalid_params or []
        super().__init__(message)


class ValidationError(SpineError):
    """Raised when data validation fails."""

    pass


class PipelineError(SpineError):
    """Raised when pipeline execution fails."""

    pass
