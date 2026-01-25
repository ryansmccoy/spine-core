"""
Tests for spine.orchestration.loader module.

Tests cover:
- YAML file loading
- Schema validation
- API version handling
- Error handling for invalid files
"""

import pytest

from spine.orchestration.loader import (
    load_group_from_yaml,
    load_groups_from_directory,
    group_to_yaml,
    validate_yaml_schema,
    SUPPORTED_API_VERSIONS,
)
from spine.orchestration.exceptions import InvalidGroupSpecError


class TestLoadGroupFromYaml:
    """Tests for load_group_from_yaml function."""

    def test_load_valid_yaml(self, yaml_fixtures_dir):
        """Test loading a valid YAML group definition."""
        yaml_path = yaml_fixtures_dir / "sample_group.yaml"

        group = load_group_from_yaml(yaml_path)

        assert group.name == "finra.weekly_refresh"
        assert group.domain == "finra.otc_transparency"
        assert len(group.steps) == 4

    def test_load_diamond_group(self, yaml_fixtures_dir):
        """Test loading diamond dependency pattern from YAML."""
        yaml_path = yaml_fixtures_dir / "diamond_group.yaml"

        group = load_group_from_yaml(yaml_path)

        assert group.name == "test.diamond"
        assert len(group.steps) == 4

        # Verify dependencies are parsed correctly
        step_d = group.get_step("step_d")
        assert set(step_d.depends_on) == {"step_b", "step_c"}

    def test_load_parallel_group(self, yaml_fixtures_dir):
        """Test loading parallel group from YAML."""
        yaml_path = yaml_fixtures_dir / "parallel_group.yaml"

        group = load_group_from_yaml(yaml_path)

        assert group.name == "test.parallel"
        assert group.policy.max_concurrency == 4

    def test_file_not_found_raises_error(self):
        """Test that missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_group_from_yaml("/nonexistent/path/group.yaml")

    def test_accepts_string_path(self, yaml_fixtures_dir):
        """Test that string path is accepted."""
        yaml_path = str(yaml_fixtures_dir / "sample_group.yaml")

        group = load_group_from_yaml(yaml_path)

        assert group is not None


class TestYamlValidation:
    """Tests for YAML schema validation."""

    def test_invalid_yaml_syntax_raises_error(self, temp_dir):
        """Test that invalid YAML syntax raises error."""
        yaml_path = temp_dir / "invalid.yaml"
        yaml_path.write_text("invalid: yaml: content: [")

        with pytest.raises(InvalidGroupSpecError):
            load_group_from_yaml(yaml_path)

    def test_non_dict_root_raises_error(self, temp_dir):
        """Test that non-dict root element raises error."""
        yaml_path = temp_dir / "array_root.yaml"
        yaml_path.write_text("- item1\n- item2")

        with pytest.raises(InvalidGroupSpecError, match="Expected dict"):
            load_group_from_yaml(yaml_path)

    def test_unsupported_api_version_raises_error(self, temp_dir):
        """Test that unsupported API version raises error."""
        yaml_content = """
apiVersion: spine.io/v99
kind: PipelineGroup
metadata:
  name: test.group
spec:
  pipelines:
    - name: a
      pipeline: pipeline.a
"""
        yaml_path = temp_dir / "unsupported_version.yaml"
        yaml_path.write_text(yaml_content)

        with pytest.raises(InvalidGroupSpecError, match="Unsupported apiVersion"):
            load_group_from_yaml(yaml_path)

    def test_wrong_kind_raises_error(self, temp_dir):
        """Test that wrong kind raises error."""
        yaml_content = """
apiVersion: spine.io/v1
kind: WrongKind
metadata:
  name: test.group
spec:
  pipelines:
    - name: a
      pipeline: pipeline.a
"""
        yaml_path = temp_dir / "wrong_kind.yaml"
        yaml_path.write_text(yaml_content)

        with pytest.raises(InvalidGroupSpecError, match="Expected kind 'PipelineGroup'"):
            load_group_from_yaml(yaml_path)


class TestSupportedApiVersions:
    """Tests for API version handling."""

    def test_supported_versions_exist(self):
        """Test that supported versions set exists."""
        assert len(SUPPORTED_API_VERSIONS) > 0

    def test_v1_is_supported(self):
        """Test that v1 API is supported."""
        assert "spine.io/v1" in SUPPORTED_API_VERSIONS


class TestYamlMetadataParsing:
    """Tests for metadata parsing from YAML."""

    def test_parses_name(self, yaml_fixtures_dir):
        """Test parsing of group name."""
        group = load_group_from_yaml(yaml_fixtures_dir / "sample_group.yaml")

        assert group.name == "finra.weekly_refresh"

    def test_parses_domain(self, yaml_fixtures_dir):
        """Test parsing of domain."""
        group = load_group_from_yaml(yaml_fixtures_dir / "sample_group.yaml")

        assert group.domain == "finra.otc_transparency"

    def test_parses_version(self, yaml_fixtures_dir):
        """Test parsing of version."""
        group = load_group_from_yaml(yaml_fixtures_dir / "sample_group.yaml")

        assert group.version == 1

    def test_parses_description(self, yaml_fixtures_dir):
        """Test parsing of description."""
        group = load_group_from_yaml(yaml_fixtures_dir / "sample_group.yaml")

        assert "FINRA" in group.description


class TestYamlSpecParsing:
    """Tests for spec section parsing from YAML."""

    def test_parses_defaults(self, yaml_fixtures_dir):
        """Test parsing of defaults."""
        group = load_group_from_yaml(yaml_fixtures_dir / "sample_group.yaml")

        assert "tier" in group.defaults
        assert group.defaults["tier"] == "NMS_TIER_1"

    def test_parses_pipelines(self, yaml_fixtures_dir):
        """Test parsing of pipelines list."""
        group = load_group_from_yaml(yaml_fixtures_dir / "sample_group.yaml")

        assert len(group.steps) == 4
        step_names = group.step_names
        assert "ingest" in step_names
        assert "normalize" in step_names

    def test_parses_depends_on(self, yaml_fixtures_dir):
        """Test parsing of depends_on."""
        group = load_group_from_yaml(yaml_fixtures_dir / "sample_group.yaml")

        normalize = group.get_step("normalize")
        assert "ingest" in normalize.depends_on

    def test_parses_policy(self, yaml_fixtures_dir):
        """Test parsing of policy."""
        group = load_group_from_yaml(yaml_fixtures_dir / "sample_group.yaml")

        assert group.policy is not None


class TestLoadGroupsFromDirectory:
    """Tests for load_groups_from_directory function."""

    def test_loads_all_yaml_files(self, yaml_fixtures_dir):
        """Test loading all YAML files from directory."""
        groups = load_groups_from_directory(yaml_fixtures_dir)

        # We have sample_group, diamond_group, parallel_group (not invalid_cycle)
        # The function loads all .yaml files that are valid
        assert len(groups) >= 3

    def test_returns_empty_for_nonexistent_directory(self, temp_dir):
        """Test that nonexistent directory returns empty list."""
        groups = load_groups_from_directory(temp_dir / "nonexistent")

        assert groups == []

    def test_custom_pattern(self, temp_dir):
        """Test loading with custom glob pattern."""
        # Create a group file with .yml extension
        yaml_content = """
apiVersion: spine.io/v1
kind: PipelineGroup
metadata:
  name: test.yml_group
spec:
  pipelines:
    - name: step_a
      pipeline: test.pipeline_a
"""
        yml_file = temp_dir / "test.yml"
        yml_file.write_text(yaml_content)

        # Load with .yml pattern
        groups = load_groups_from_directory(temp_dir, pattern="*.yml")

        assert len(groups) == 1
        assert groups[0].name == "test.yml_group"

    def test_ignore_errors_skips_invalid_files(self, temp_dir):
        """Test that ignore_errors=True skips invalid files."""
        # Create one valid file
        valid_content = """
apiVersion: spine.io/v1
kind: PipelineGroup
metadata:
  name: test.valid
spec:
  pipelines:
    - name: step_a
      pipeline: test.pipeline_a
"""
        valid_file = temp_dir / "valid.yaml"
        valid_file.write_text(valid_content)

        # Create one invalid file
        invalid_file = temp_dir / "invalid.yaml"
        invalid_file.write_text("invalid: yaml: [")

        # Load with ignore_errors=True
        groups = load_groups_from_directory(temp_dir, ignore_errors=True)

        assert len(groups) == 1
        assert groups[0].name == "test.valid"

    def test_ignore_errors_false_raises_on_invalid(self, temp_dir):
        """Test that ignore_errors=False raises on invalid files."""
        # Create an invalid file
        invalid_file = temp_dir / "invalid.yaml"
        invalid_file.write_text("invalid: yaml: [")

        with pytest.raises(InvalidGroupSpecError):
            load_groups_from_directory(temp_dir, ignore_errors=False)


class TestGroupToYaml:
    """Tests for group_to_yaml function."""

    def test_roundtrip_load_and_dump(self, yaml_fixtures_dir):
        """Test that loading and dumping produces valid YAML."""
        original = load_group_from_yaml(yaml_fixtures_dir / "sample_group.yaml")

        yaml_str = group_to_yaml(original)

        # Verify it's valid YAML
        import yaml
        parsed = yaml.safe_load(yaml_str)

        assert parsed["apiVersion"] == "spine.io/v1"
        assert parsed["kind"] == "PipelineGroup"
        assert parsed["metadata"]["name"] == original.name

    def test_includes_metadata(self, yaml_fixtures_dir):
        """Test that metadata is included in output."""
        group = load_group_from_yaml(yaml_fixtures_dir / "sample_group.yaml")

        yaml_str = group_to_yaml(group)
        import yaml
        parsed = yaml.safe_load(yaml_str)

        assert parsed["metadata"]["name"] == group.name
        assert parsed["metadata"]["domain"] == group.domain
        assert parsed["metadata"]["version"] == group.version

    def test_includes_pipelines(self, yaml_fixtures_dir):
        """Test that pipelines are included in output."""
        group = load_group_from_yaml(yaml_fixtures_dir / "sample_group.yaml")

        yaml_str = group_to_yaml(group)
        import yaml
        parsed = yaml.safe_load(yaml_str)

        pipelines = parsed["spec"]["pipelines"]
        assert len(pipelines) == len(group.steps)

    def test_includes_policy(self, yaml_fixtures_dir):
        """Test that policy is included in output."""
        group = load_group_from_yaml(yaml_fixtures_dir / "sample_group.yaml")

        yaml_str = group_to_yaml(group)
        import yaml
        parsed = yaml.safe_load(yaml_str)

        policy = parsed["spec"]["policy"]
        assert "execution" in policy
        assert "max_concurrency" in policy
        assert "on_failure" in policy

    def test_includes_defaults_when_present(self, yaml_fixtures_dir):
        """Test that defaults are included when present."""
        group = load_group_from_yaml(yaml_fixtures_dir / "sample_group.yaml")

        yaml_str = group_to_yaml(group)
        import yaml
        parsed = yaml.safe_load(yaml_str)

        if group.defaults:
            assert "defaults" in parsed["spec"]
            assert parsed["spec"]["defaults"] == group.defaults


class TestValidateYamlSchema:
    """Tests for validate_yaml_schema function."""

    def test_valid_yaml_returns_empty_list(self):
        """Test that valid YAML returns no errors."""
        data = {
            "metadata": {
                "name": "test.group",
            },
            "spec": {
                "pipelines": [
                    {"name": "step_a", "pipeline": "test.pipeline"},
                ]
            }
        }

        errors = validate_yaml_schema(data)

        assert errors == []

    def test_missing_name_returns_error(self):
        """Test that missing name returns error."""
        data = {
            "metadata": {},
            "spec": {
                "pipelines": [
                    {"name": "step_a", "pipeline": "test.pipeline"},
                ]
            }
        }

        errors = validate_yaml_schema(data)

        assert any("name is required" in e for e in errors)

    def test_missing_pipelines_returns_error(self):
        """Test that missing pipelines returns error."""
        data = {
            "metadata": {
                "name": "test.group",
            },
            "spec": {}
        }

        errors = validate_yaml_schema(data)

        assert any("pipelines is required" in e for e in errors)

    def test_pipeline_without_name_returns_error(self):
        """Test that pipeline without name returns error."""
        data = {
            "metadata": {
                "name": "test.group",
            },
            "spec": {
                "pipelines": [
                    {"pipeline": "test.pipeline"},  # missing name
                ]
            }
        }

        errors = validate_yaml_schema(data)

        assert any("pipelines[0].name is required" in e for e in errors)

    def test_pipeline_without_pipeline_ref_returns_error(self):
        """Test that pipeline without pipeline ref returns error."""
        data = {
            "metadata": {
                "name": "test.group",
            },
            "spec": {
                "pipelines": [
                    {"name": "step_a"},  # missing pipeline
                ]
            }
        }

        errors = validate_yaml_schema(data)

        assert any("pipelines[0].pipeline is required" in e for e in errors)

    def test_flat_format_without_name_returns_error(self):
        """Test flat format validation - missing name."""
        data = {
            "steps": [
                {"name": "step_a", "pipeline": "test.pipeline"},
            ]
        }

        errors = validate_yaml_schema(data)

        assert any("name is required" in e for e in errors)

    def test_flat_format_without_steps_returns_error(self):
        """Test flat format validation - missing steps."""
        data = {
            "name": "test.group",
        }

        errors = validate_yaml_schema(data)

        assert any("steps or pipelines is required" in e for e in errors)

    def test_flat_format_with_pipelines_is_valid(self):
        """Test flat format with pipelines key is valid."""
        data = {
            "name": "test.group",
            "pipelines": [
                {"name": "step_a", "pipeline": "test.pipeline"},
            ]
        }

        errors = validate_yaml_schema(data)

        # No 'steps or pipelines required' error
        assert not any("steps or pipelines is required" in e for e in errors)
