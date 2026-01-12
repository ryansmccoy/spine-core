"""Tests for spine.core.result module."""

import pytest

from spine.core.result import Result, Ok, Err
from spine.core.errors import SourceError, ValidationError


class TestOk:
    """Test Ok class."""

    def test_create_ok(self):
        """Create Ok with value."""
        result = Ok(42)
        assert result.value == 42
        assert result.is_ok() is True
        assert result.is_err() is False

    def test_unwrap(self):
        """unwrap returns value for Ok."""
        result = Ok("hello")
        assert result.unwrap() == "hello"

    def test_unwrap_or(self):
        """unwrap_or returns value for Ok."""
        result = Ok(10)
        assert result.unwrap_or(99) == 10

    def test_unwrap_or_else(self):
        """unwrap_or_else returns value for Ok."""
        result = Ok(20)
        assert result.unwrap_or_else(lambda e: 99) == 20

    def test_map(self):
        """map transforms the value."""
        result = Ok(5).map(lambda x: x * 2)
        assert result.unwrap() == 10

    def test_map_chaining(self):
        """map can be chained."""
        result = Ok(3).map(lambda x: x * 2).map(lambda x: x + 1)
        assert result.unwrap() == 7

    def test_flat_map(self):
        """flat_map chains Result-returning functions."""
        def double_if_even(x: int) -> Result[int]:
            if x % 2 == 0:
                return Ok(x * 2)
            return Err(ValueError("Odd number"))
        
        result = Ok(4).flat_map(double_if_even)
        assert result.unwrap() == 8
        
        result = Ok(3).flat_map(double_if_even)
        assert result.is_err()

    def test_and_then(self):
        """and_then is alias for flat_map."""
        result = Ok(10).and_then(lambda x: Ok(x + 5))
        assert result.unwrap() == 15

    def test_map_err_no_op(self):
        """map_err is no-op for Ok."""
        result = Ok(42).map_err(lambda e: ValueError("new error"))
        assert result.unwrap() == 42

    def test_or_else_returns_self(self):
        """or_else returns self for Ok."""
        result = Ok(42).or_else(lambda e: Ok(99))
        assert result.unwrap() == 42

    def test_inspect(self):
        """inspect calls function with value."""
        side_effect = []
        result = Ok(42).inspect(lambda x: side_effect.append(x))
        assert side_effect == [42]
        assert result.unwrap() == 42

    def test_inspect_err_no_op(self):
        """inspect_err is no-op for Ok."""
        side_effect = []
        result = Ok(42).inspect_err(lambda e: side_effect.append(e))
        assert side_effect == []

    def test_to_dict(self):
        """to_dict serializes Ok."""
        result = Ok({"key": "value"})
        d = result.to_dict()
        assert d["ok"] is True
        assert d["value"] == {"key": "value"}

    def test_ok_is_immutable(self):
        """Ok is immutable."""
        result = Ok(42)
        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            result.value = 99


class TestErr:
    """Test Err class."""

    def test_create_err(self):
        """Create Err with error."""
        error = ValueError("Bad value")
        result = Err(error)
        assert result.error == error
        assert result.is_ok() is False
        assert result.is_err() is True

    def test_unwrap_raises(self):
        """unwrap raises the error."""
        error = ValueError("Bad value")
        result = Err(error)
        with pytest.raises(ValueError, match="Bad value"):
            result.unwrap()

    def test_unwrap_or(self):
        """unwrap_or returns default for Err."""
        result = Err(ValueError("error"))
        assert result.unwrap_or(99) == 99

    def test_unwrap_or_else(self):
        """unwrap_or_else calls function with error."""
        result = Err(ValueError("error"))
        assert result.unwrap_or_else(lambda e: 42) == 42

    def test_map_no_op(self):
        """map is no-op for Err."""
        result = Err(ValueError("error")).map(lambda x: x * 2)
        assert result.is_err()

    def test_flat_map_no_op(self):
        """flat_map is no-op for Err."""
        result = Err(ValueError("error")).flat_map(lambda x: Ok(x * 2))
        assert result.is_err()

    def test_map_err(self):
        """map_err transforms the error."""
        result = Err(ValueError("original")).map_err(
            lambda e: SourceError("wrapped", cause=e)
        )
        assert result.is_err()
        assert isinstance(result.error, SourceError)

    def test_or_else(self):
        """or_else provides alternative Result."""
        result = Err(ValueError("error")).or_else(lambda e: Ok(42))
        assert result.unwrap() == 42

    def test_inspect_no_op(self):
        """inspect is no-op for Err."""
        side_effect = []
        result = Err(ValueError("error")).inspect(lambda x: side_effect.append(x))
        assert side_effect == []

    def test_inspect_err(self):
        """inspect_err calls function with error."""
        side_effect = []
        error = ValueError("test error")
        result = Err(error).inspect_err(lambda e: side_effect.append(e))
        assert side_effect == [error]

    def test_to_dict(self):
        """to_dict serializes Err."""
        error = SourceError("Source failed")
        result = Err(error)
        d = result.to_dict()
        assert d["ok"] is False
        assert "error" in d

    def test_err_is_immutable(self):
        """Err is immutable."""
        result = Err(ValueError("error"))
        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            result.error = ValueError("new")


class TestPatternMatching:
    """Test pattern matching with Result."""

    def test_match_ok(self):
        """Pattern match on Ok."""
        result = Ok(42)
        match result:
            case Ok(value):
                assert value == 42
            case Err(error):
                pytest.fail("Should not match Err")

    def test_match_err(self):
        """Pattern match on Err."""
        result = Err(ValueError("error"))
        match result:
            case Ok(value):
                pytest.fail("Should not match Ok")
            case Err(error):
                assert isinstance(error, ValueError)


class TestChainingExamples:
    """Test realistic chaining examples."""

    def test_parse_and_validate(self):
        """Chain parsing and validation."""
        def parse_int(s: str) -> Result[int]:
            try:
                return Ok(int(s))
            except ValueError as e:
                return Err(e)
        
        def validate_positive(n: int) -> Result[int]:
            if n > 0:
                return Ok(n)
            return Err(ValidationError("Must be positive"))
        
        # Success case
        result = parse_int("42").flat_map(validate_positive)
        assert result.unwrap() == 42
        
        # Parse failure
        result = parse_int("not a number").flat_map(validate_positive)
        assert result.is_err()
        
        # Validation failure
        result = parse_int("-5").flat_map(validate_positive)
        assert result.is_err()

    def test_map_chain(self):
        """Chain multiple transformations."""
        result = (
            Ok(10)
            .map(lambda x: x * 2)
            .map(lambda x: x + 5)
            .map(lambda x: f"Result: {x}")
        )
        assert result.unwrap() == "Result: 25"

    def test_error_propagation(self):
        """Errors propagate through chain."""
        result = (
            Err(ValueError("initial error"))
            .map(lambda x: x * 2)
            .map(lambda x: x + 5)
        )
        assert result.is_err()
        assert isinstance(result.error, ValueError)

    def test_recover_from_error(self):
        """Use or_else to recover from error."""
        def fetch_primary() -> Result[str]:
            return Err(SourceError("Primary down"))
        
        def fetch_backup(e: Exception) -> Result[str]:
            return Ok("backup data")
        
        result = fetch_primary().or_else(fetch_backup)
        assert result.unwrap() == "backup data"
