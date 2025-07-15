#!/usr/bin/env python3
"""Send a debug break command to the running MCP server."""

import socket
import sys

def send_break():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(('localhost', 9999))
        sock.send(b'BREAK\n')
        response = sock.recv(1024).decode()
        print(f"Server response: {response.strip()}")
        sock.close()
        print("Debug break triggered! Check the MCP server terminal.")
    except ConnectionRefusedError:
        print("Could not connect to debug server on localhost:9999")
        print("Make sure the MCP server is running with debug_server_wrapper.py")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    send_break()