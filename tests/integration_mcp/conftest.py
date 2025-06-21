"""
Configuration for MCP integration tests.
These tests use adapter-level mocking to test the MCP protocol interface.
"""
import os
import pytest

# Set adapter mocking for MCP tests
os.environ["MCP_ADAPTER_MOCK"] = "1"