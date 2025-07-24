"""Unit tests for ParameterRouter routing logic."""

from typing import List
from mcp_the_force.tools.parameter_router import ParameterRouter
from mcp_the_force.tools.descriptors import Route, RouteType
from mcp_the_force.tools.base import ToolSpec
from mcp_the_force.tools.registry import ToolMetadata, ParameterInfo


class TestParameterRouter:
    def test_vector_store_ids_routing(self):
        class TestTool(ToolSpec):
            query: str = Route.prompt()
            vs_ids: List[str] = Route.vector_store_ids(default_factory=list)

        metadata = ToolMetadata(
            id="test_tool",
            spec_class=TestTool,
            model_config={
                "adapter_class": "mock",
                "model_name": "mock",
                "context_window": 0,
                "timeout": 1,
                "description": "",
            },
            parameters={
                "query": ParameterInfo(
                    name="query",
                    type=str,
                    type_str="str",
                    route=RouteType.PROMPT,
                    position=None,
                    default=None,
                    required=True,
                    description="",
                ),
                "vs_ids": ParameterInfo(
                    name="vs_ids",
                    type=List[str],
                    type_str="List[str]",
                    route=RouteType.VECTOR_STORE_IDS,
                    position=None,
                    default=[],
                    required=False,
                    description="",
                ),
            },
            aliases=[],
        )

        router = ParameterRouter()
        params = {"query": "foo", "vs_ids": ["id1", "id2"]}
        routed = router.route(metadata, params)
        assert routed["vector_store_ids"] == ["id1", "id2"]
