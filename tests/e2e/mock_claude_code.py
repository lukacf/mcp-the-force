#!/usr/bin/env python3
"""Mock Claude Code CLI for E2E testing.

This simulates the behavior of Claude Code CLI to enable E2E testing
without requiring the actual Claude Code binary.
"""
import sys
import json
import re
import subprocess
import os
from pathlib import Path


def main():
    """Main entry point for mock Claude Code."""
    if len(sys.argv) < 2:
        print("Usage: claude [options] [command]")
        sys.exit(1)
    
    # Handle --version
    if sys.argv[1] == "--version":
        print("claude-code mock version 0.1.0")
        sys.exit(0)
    
    # Handle mcp add-json
    if len(sys.argv) >= 3 and sys.argv[1] == "mcp" and sys.argv[2] == "add-json":
        print(f"Added MCP server: {sys.argv[3] if len(sys.argv) > 3 else 'unknown'}")
        sys.exit(0)
    
    # Handle -p --dangerously-skip-permissions [prompt]
    if len(sys.argv) >= 4 and sys.argv[1] == "-p" and sys.argv[2] == "--dangerously-skip-permissions":
        prompt = sys.argv[3]
        handle_prompt(prompt)
        sys.exit(0)
    
    print(f"Mock Claude Code - unknown command: {' '.join(sys.argv[1:])}")
    sys.exit(1)


def handle_prompt(prompt: str):
    """Handle a prompt that asks to use the MCP server."""
    # Parse the prompt to extract the tool and arguments
    if "list_models" in prompt:
        # Simulate list_models response
        print("Available models:")
        print("- gemini25_pro: Deep analysis and multimodal understanding")
        print("- gemini25_flash: Fast summarization and quick analysis")
        print("- o3: Chain-of-thought reasoning and algorithm design")
        print("- o3_pro: Deep analysis and formal reasoning")
        print("- gpt4_1: Fast long-context processing")
        return
    
    # Try to extract tool name and arguments from prompt
    tool_match = re.search(r'chat_with_(\w+)', prompt)
    if not tool_match:
        print("Mock response: Could not identify which tool to use")
        return
    
    tool_name = f"chat_with_{tool_match.group(1)}"
    
    # Extract JSON arguments if present
    json_match = re.search(r'\{[^}]+\}', prompt)
    if json_match:
        try:
            args = json.loads(json_match.group(0))
        except json.JSONDecodeError:
            args = {
                "instructions": "Say hello",
                "output_format": "text",
                "context": []
            }
    else:
        # Try to parse natural language
        args = parse_natural_language_args(prompt)
    
    # Actually call the MCP server
    try:
        result = call_mcp_server(tool_name, args)
        print(result)
    except Exception as e:
        print(f"Error calling MCP server: {e}")


def parse_natural_language_args(prompt: str) -> dict:
    """Parse arguments from natural language prompt."""
    args = {
        "instructions": "Say hello",
        "output_format": "text",
        "context": []
    }
    
    # Extract instructions
    inst_match = re.search(r'instructions\s+"([^"]+)"', prompt)
    if inst_match:
        args["instructions"] = inst_match.group(1)
    
    # Extract output format
    format_match = re.search(r'output_format\s+"([^"]+)"', prompt)
    if format_match:
        args["output_format"] = format_match.group(1)
    
    # Extract context
    context_match = re.search(r'context\s+\[([^\]]+)\]', prompt)
    if context_match:
        # Parse the context list
        context_str = context_match.group(1)
        # Extract quoted strings
        contexts = re.findall(r'"([^"]+)"', context_str)
        args["context"] = contexts
    
    # Handle session_id for OpenAI models
    if "o3" in prompt or "gpt4_1" in prompt:
        args["session_id"] = "test-session"
    
    return args


def call_mcp_server(tool_name: str, args: dict) -> str:
    """Actually invoke the MCP server with the given tool and arguments."""
    # Build the MCP request
    request = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": args
        },
        "id": 1
    }
    
    # Start the MCP server process
    env = os.environ.copy()
    env["MCP_ADAPTER_MOCK"] = "0"  # Use real adapters for E2E tests
    
    process = subprocess.Popen(
        ["uv", "run", "--", "mcp-second-brain"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env
    )
    
    # Send the request
    request_str = json.dumps(request) + "\n"
    stdout, stderr = process.communicate(input=request_str, timeout=180)
    
    if process.returncode != 0:
        return f"MCP server error: {stderr}"
    
    # Parse the response
    try:
        # The stdout might contain multiple lines, find the JSON-RPC response
        for line in stdout.strip().split('\n'):
            if line.strip().startswith('{'):
                response = json.loads(line)
                if "result" in response:
                    # Extract the actual content from the result
                    result = response["result"]
                    if isinstance(result, dict) and "content" in result:
                        content = result["content"]
                        if isinstance(content, list) and len(content) > 0:
                            return content[0].get("text", str(content))
                    return str(result)
                elif "error" in response:
                    return f"MCP error: {response['error']}"
    except json.JSONDecodeError:
        pass
    
    return f"Mock response: {stdout}"


if __name__ == "__main__":
    main()