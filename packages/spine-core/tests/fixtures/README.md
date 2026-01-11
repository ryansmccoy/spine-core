# Test Fixtures Directory
# 
# This directory contains fixture data for spine-core tests.
#
# Structure:
#   yaml/           - YAML group definitions for loader tests
#   golden/         - Expected outputs for snapshot/golden tests
#
# Adding New Fixtures:
#   1. Create the fixture file in the appropriate subdirectory
#   2. Use descriptive names: {purpose}_{variant}.yaml
#   3. Add comments explaining what the fixture tests
#   4. Reference in tests using the fixtures_dir fixture from conftest.py
