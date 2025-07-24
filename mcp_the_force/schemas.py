from typing import Any, Dict, List
from typing_extensions import TypedDict


class ToolDescriptor(TypedDict):
    name: str
    description: str
    inputSchema: Dict
    annotations: Dict


class ListToolsResult(TypedDict):
    tools: List[ToolDescriptor]


class CallToolParams(TypedDict):
    name: str
    arguments: Dict[str, Any]


class CallToolResult(TypedDict, total=False):
    isError: bool
    content: List[Dict[str, Any]]
