# Packages Overview

Spine-Core contains several shared packages used across the Spine Ecosystem.

## Available Packages

### doc-automation

Automatically extracts documentation from source code annotations and generates Markdown files for the documentation site.

**Features:**
- Extract annotations from Python source files
- Generate ARCHITECTURE.md, FEATURES.md, API_REFERENCE.md
- Support for custom annotation formats
- MkDocs integration

### config-spine

Unified configuration management across all Spine projects.

**Features:**
- Environment-based configuration
- Hierarchical config merging
- Type validation
- Secrets management

### shared-utils

Common utilities and helpers used across Spine projects.

**Features:**
- Result[T] pattern for error handling
- ExecutionContext for pipeline execution
- Logging utilities
- Path helpers
