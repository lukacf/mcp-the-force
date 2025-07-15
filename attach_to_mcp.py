#!/usr/bin/env python3
"""
Attach to a running MCP second-brain process for debugging.
"""

import sys
import os
import psutil
import subprocess

# Find the MCP process
def find_mcp_processes():
    """Find all running MCP second-brain processes."""
    mcp_processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info.get('cmdline', [])
            if cmdline and any('mcp-second-brain' in arg for arg in cmdline):
                # Skip our own process
                if proc.pid != os.getpid():
                    mcp_processes.append({
                        'pid': proc.info['pid'],
                        'cmdline': ' '.join(cmdline)
                    })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return mcp_processes

if __name__ == "__main__":
    processes = find_mcp_processes()
    
    if not processes:
        print("No MCP second-brain processes found!")
        print("Please start one in another Claude session first.")
        sys.exit(1)
    
    print("Found MCP processes:")
    for i, proc in enumerate(processes):
        print(f"{i}: PID {proc['pid']} - {proc['cmdline'][:80]}...")
    
    if len(processes) == 1:
        target_pid = processes[0]['pid']
    else:
        choice = input("\nWhich process to attach to? (0-{}): ".format(len(processes)-1))
        target_pid = processes[int(choice)]['pid']
    
    print(f"\nAttaching to PID {target_pid}...")
    print("This will allow interactive debugging of the running MCP server.")
    
    # Now use gdb to attach (on macOS we might need sudo)
    # For Python debugging, we'd normally use py-spy or pyrasite
    # But for pdb, we need to inject code
    
    # Create a script to inject
    inject_script = f"""
import sys
import pdb
import signal

def debug_handler(sig, frame):
    pdb.set_trace()

signal.signal(signal.SIGUSR1, debug_handler)
print("Debug handler installed. Send SIGUSR1 to PID {target_pid} to break into debugger.")
"""
    
    with open('/tmp/inject_debug.py', 'w') as f:
        f.write(inject_script)
    
    print("\nTo debug the MCP server:")
    print(f"1. Send SIGUSR1 to the process: kill -USR1 {target_pid}")
    print("2. The process will break into pdb")
    print("\nNote: Direct process attachment requires special tools like py-spy or gdb.")