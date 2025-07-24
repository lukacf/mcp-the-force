"""Integration test for file tree in prompt building."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
from lxml import etree as ET

from mcp_the_force.tools.executor import ToolExecutor
from mcp_the_force.tools.registry import ToolMetadata


@pytest.mark.asyncio
async def test_file_tree_in_prompt():
    """Test that file tree is correctly included in the prompt."""

    # Create tool executor
    executor = ToolExecutor()

    # Create mock metadata
    metadata = MagicMock(spec=ToolMetadata)
    metadata.id = "test_tool"
    metadata.spec_class = MagicMock()
    metadata.model_config = {
        "adapter_class": "openai",
        "model_name": "test-model",
        "timeout": 10,
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test files
        root = Path(tmpdir)
        (root / "src").mkdir()
        (root / "src" / "main.py").write_text("print('hello')")
        (root / "src" / "utils.py").write_text("# utils")
        (root / "tests").mkdir()
        (root / "tests" / "test_main.py").write_text("# test")
        (root / "data.csv").write_text("col1,col2\\n1,2")

        context_paths = [str(root / "src")]
        attachment_paths = [str(root / "data.csv")]

        # Mock dependencies
        with (
            patch.object(executor.validator, "validate") as mock_validate,
            patch.object(executor.router, "route") as mock_route,
            patch("mcp_the_force.config.get_settings") as mock_settings,
            patch(
                "mcp_the_force.utils.thread_pool.get_settings"
            ) as mock_thread_settings,
            patch("mcp_the_force.adapters.get_adapter") as mock_get_adapter,
            patch(
                "mcp_the_force.adapters.model_registry.get_model_context_window",
                return_value=100000,
            ),
            patch("mcp_the_force.utils.fs.gather_file_paths_async") as mock_gather,
            patch(
                "mcp_the_force.utils.context_loader.load_specific_files_async"
            ) as mock_load,
        ):
            # Setup mocks
            mock_validate.return_value = {
                "instructions": "Test instructions",
                "output_format": "Test output",
                "context": context_paths,
                "attachments": attachment_paths,
                "session_id": "test_session",
            }

            mock_route.return_value = {
                "prompt": {
                    "instructions": "Test instructions",
                    "output_format": "Test output",
                    "context": context_paths,
                },
                "adapter": {},
                "session": {"session_id": "test_session"},
                "vector_store": attachment_paths,
                "vector_store_ids": [],
                "structured_output": {},
            }

            mock_settings.return_value.mcp.context_percentage = 0.85
            mock_settings.return_value.memory_enabled = False

            mock_thread_settings.return_value.mcp.thread_pool_workers = 4

            # Mock file gathering
            mock_gather.side_effect = (
                lambda paths, **kwargs: [
                    str(root / "src" / "main.py"),
                    str(root / "src" / "utils.py"),
                    str(root / "tests" / "test_main.py"),
                ]
                if "src" in str(paths[0])
                else [str(root / "data.csv")]
            )

            # Mock file loading
            mock_load.return_value = [
                (str(root / "src" / "main.py"), "print('hello')", 10),
                (str(root / "src" / "utils.py"), "# utils", 5),
            ]

            # Mock adapter
            mock_adapter = AsyncMock()
            mock_adapter.generate = AsyncMock(return_value="Test response")
            mock_get_adapter.return_value = (mock_adapter, None)

            # Execute
            await executor.execute(
                metadata=metadata,
                instructions="Test instructions",
                output_format="Test output",
                context=context_paths,
                attachments=attachment_paths,
                session_id="test_session",
            )

            # Check that generate was called
            assert mock_adapter.generate.called

            # Get the prompt that was passed
            prompt = mock_adapter.generate.call_args[1]["prompt"]

            # The prompt may have additional instructions at the end
            # Split to get just the XML part
            xml_end = prompt.find("</Task>")
            if xml_end != -1:
                xml_part = prompt[: xml_end + len("</Task>")]
            else:
                xml_part = prompt

            # Parse the XML prompt
            root_elem = ET.fromstring(xml_part)

            # Check that file_map exists
            file_map = root_elem.find(".//file_map")
            assert file_map is not None

            file_map_text = file_map.text
            assert file_map_text is not None

            # Check legend
            assert "Legend:" in file_map_text
            assert "attached" in file_map_text
            assert "search_task_files" in file_map_text

            # Check that files are shown with correct markers
            # Since we mocked the file tree building, we should see our files
            # The inline files should not have "attached" marker
            # The attachment files should have "attached" marker

            # Check CONTEXT section exists
            context_elem = root_elem.find(".//CONTEXT")
            assert context_elem is not None

            # Check that inline files are in CONTEXT
            file_elements = context_elem.findall(".//file")
            assert len(file_elements) == 2  # main.py and utils.py

            paths_in_context = [Path(f.get("path")).resolve() for f in file_elements]
            assert (root / "src" / "main.py").resolve() in paths_in_context
            assert (root / "src" / "utils.py").resolve() in paths_in_context
