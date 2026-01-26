"""
Configuration for Documentation Automation.

Manages settings for parsing, graph building, and doc generation.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import yaml


@dataclass
class DocAutomationConfig:
    """Configuration for documentation automation system.
    
    Attributes:
        project_root: Root directory of the project to document
        output_dir: Where to write generated documentation
        template_dir: Directory containing Jinja2 templates
        skip_patterns: Patterns to skip when scanning files
        doc_types: Document types to generate
        tier_1_classes: List of class patterns that MUST be annotated
    """
    
    project_root: Path = field(default_factory=lambda: Path("."))
    output_dir: Path = field(default_factory=lambda: Path("docs"))
    template_dir: Path | None = None
    
    # File scanning
    skip_patterns: list[str] = field(default_factory=lambda: [
        "test_", "__pycache__", ".pyc", "venv", ".venv", 
        "node_modules", ".git", "build", "dist"
    ])
    
    # Document types to generate
    doc_types: list[str] = field(default_factory=lambda: [
        "MANIFESTO",
        "FEATURES",
        "GUARDRAILS",
        "ARCHITECTURE",
        "API_REFERENCE",
    ])
    
    # Tier 1 classes (MUST be annotated)
    tier_1_classes: list[str] = field(default_factory=list)
    
    # Quality thresholds
    min_manifesto_length: int = 100
    min_tags_per_class: int = 3
    min_doc_types_per_class: int = 2
    
    # Generation options
    include_source_links: bool = True
    include_timestamps: bool = True
    
    def __post_init__(self):
        """Convert paths to Path objects if strings."""
        if isinstance(self.project_root, str):
            self.project_root = Path(self.project_root)
        if isinstance(self.output_dir, str):
            self.output_dir = Path(self.output_dir)
        if isinstance(self.template_dir, str):
            self.template_dir = Path(self.template_dir)
        
        # Set default template dir if not specified
        if self.template_dir is None:
            self.template_dir = Path(__file__).parent / "templates"
    
    @classmethod
    def from_yaml(cls, yaml_path: Path) -> "DocAutomationConfig":
        """Load configuration from YAML file.
        
        Args:
            yaml_path: Path to YAML configuration file
            
        Returns:
            DocAutomationConfig instance
        """
        with open(yaml_path) as f:
            data = yaml.safe_load(f)
        
        return cls(**data)
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DocAutomationConfig":
        """Create config from dictionary.
        
        Args:
            data: Configuration dictionary
            
        Returns:
            DocAutomationConfig instance
        """
        return cls(**data)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary.
        
        Returns:
            Configuration as dictionary
        """
        return {
            "project_root": str(self.project_root),
            "output_dir": str(self.output_dir),
            "template_dir": str(self.template_dir) if self.template_dir else None,
            "skip_patterns": self.skip_patterns,
            "doc_types": self.doc_types,
            "tier_1_classes": self.tier_1_classes,
            "min_manifesto_length": self.min_manifesto_length,
            "min_tags_per_class": self.min_tags_per_class,
            "min_doc_types_per_class": self.min_doc_types_per_class,
            "include_source_links": self.include_source_links,
            "include_timestamps": self.include_timestamps,
        }
    
    def should_skip(self, file_path: Path) -> bool:
        """Check if a file should be skipped during scanning.
        
        Args:
            file_path: Path to check
            
        Returns:
            True if file should be skipped
        """
        path_str = str(file_path)
        return any(pattern in path_str for pattern in self.skip_patterns)


# Default configuration
DEFAULT_CONFIG = DocAutomationConfig()
