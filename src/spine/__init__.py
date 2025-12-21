"""
Spine - Data operation platform primitives.

This is a namespace package that can be extended by:
- spine.core: Core primitives (from spine-core)
- spine.framework: Application framework (from spine-core)
- spine.domains.*: Domain packages (from spine-domains-*)
"""

# Declare this as a namespace package
__path__ = __import__("pkgutil").extend_path(__path__, __name__)

__version__ = "0.4.0"

# Re-export everything from the actual implementation
from spine.core import *  # noqa
