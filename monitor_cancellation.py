#!/usr/bin/env python3
"""
Monitor MCP server logs for cancellation events in real-time.
Run this while testing aborts in another Claude session.
"""

import time
import os
from datetime import datetime
import subprocess
import threading

class CancellationMonitor:
    def __init__(self):
        self.start_time = time.time()
        self.abort_detected = False
        self.cancellation_detected = False
        self.files_to_monitor = [
            "mcp_cancellation_debug.log",
            "mcp_debug_trace.log",
            "logs/mcp_second_brain.log"
        ]
        
    def monitor_file(self, filepath):
        """Monitor a single file for cancellation events."""
        last_size = 0
        
        while True:
            try:
                if os.path.exists(filepath):
                    current_size = os.path.getsize(filepath)
                    if current_size > last_size:
                        with open(filepath, 'r') as f:
                            f.seek(last_size)
                            new_lines = f.readlines()
                            for line in new_lines:
                                self.process_line(line, filepath)
                        last_size = current_size
            except Exception as e:
                print(f"Error monitoring {filepath}: {e}")
            
            time.sleep(0.1)  # Check every 100ms
    
    def process_line(self, line, source):
        """Process a log line and detect important events."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        # Detect key events
        if "Tool execution started" in line and "chat_with_o3" in line:
            print(f"\n[{timestamp}] 🚀 O3 TOOL STARTED")
            self.abort_detected = False
            self.cancellation_detected = False
            
        elif "cancelled" in line.lower() or "cancel" in line.lower():
            if not self.cancellation_detected:
                elapsed = time.time() - self.start_time
                print(f"\n[{timestamp}] ❌ CANCELLATION DETECTED (after {elapsed:.1f}s)")
                print(f"    Source: {source}")
                print(f"    Line: {line.strip()}")
                self.cancellation_detected = True
                
        elif "ErrorData" in line or "error_response" in line:
            print(f"\n[{timestamp}] ⚠️  ERROR RESPONSE")
            print(f"    Line: {line.strip()}")
            
        elif "BrokenResourceError" in line or "broken pipe" in line.lower():
            print(f"\n[{timestamp}] 🔌 DISCONNECTION")
            print(f"    Line: {line.strip()}")
            
        elif "request already responded" in line.lower():
            print(f"\n[{timestamp}] 💥 DOUBLE RESPONSE ERROR")
            print(f"    Line: {line.strip()}")
    
    def run(self):
        """Start monitoring all log files."""
        print("=== MCP Cancellation Monitor Started ===")
        print(f"Monitoring files: {self.files_to_monitor}")
        print("\nWaiting for events...")
        print("(Start an o3 query in another Claude session and abort it)")
        print("-" * 60)
        
        # Start monitoring threads for each file
        threads = []
        for filepath in self.files_to_monitor:
            thread = threading.Thread(target=self.monitor_file, args=(filepath,))
            thread.daemon = True
            thread.start()
            threads.append(thread)
        
        # Keep main thread alive
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n\nMonitor stopped.")

if __name__ == "__main__":
    # Clear the debug log for a fresh start
    try:
        with open("mcp_cancellation_debug.log", "w") as f:
            f.write(f"[CLEARED] Monitor started at {datetime.now()}\n")
    except:
        pass
    
    monitor = CancellationMonitor()
    monitor.run()