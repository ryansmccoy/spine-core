"""Pytest configuration and shared fixtures."""

import pytest
from pathlib import Path


@pytest.fixture(scope="session")
def project_root():
    """Root directory of the doc-automation package."""
    return Path(__file__).parent.parent


@pytest.fixture(scope="session")
def fixtures_path():
    """Path to test fixtures."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def sample_class_path(fixtures_path):
    """Path to sample annotated class."""
    return fixtures_path / "sample_annotated_class.py"


@pytest.fixture
def temp_output_dir(tmp_path):
    """Temporary output directory for generated docs."""
    output_dir = tmp_path / "generated_docs"
    output_dir.mkdir()
    return output_dir


@pytest.fixture
def sample_extended_docstring():
    """Sample docstring with all extended sections."""
    return '''
    Summary line for the class.

    Manifesto:
        This is why this class exists.
        It embodies a core principle.

    Architecture:
        ```
        Input ──► Process ──► Output
        ```

    Features:
        - Feature A
        - Feature B
        - Feature C

    Examples:
        >>> obj = Class()
        >>> obj.do_thing()
        'result'

    Guardrails:
        - Do NOT do X
          ✅ Instead do Y

    Context:
        Background information about the problem domain.

    ADR:
        - 001-some-decision.md: Why we chose this approach

    Changelog:
        - v0.1.0: Initial implementation
        - v0.2.0: Added feature B

    Tags:
        - tag_one
        - tag_two

    Doc-Types:
        - MANIFESTO (section: "Core", priority: 10)
        - FEATURES (section: "Main", priority: 8)
    '''


@pytest.fixture
def sample_source_info():
    """Sample source information dict."""
    return {
        "file": "test_module.py",
        "class": "TestClass",
        "method": None,
        "line": 10,
    }


@pytest.fixture
def simple_docstring():
    """Simple docstring without extended sections."""
    return '''
    A simple class that does something.
    
    This is just a regular docstring without extended sections.
    
    Args:
        value: Some input value
        
    Returns:
        Some output value
    '''
