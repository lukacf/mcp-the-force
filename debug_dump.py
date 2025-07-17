#!/usr/bin/env python3
"""Debug helper to dump system state when hanging occurs."""

import asyncio
import traceback
import sys
import logging
import threading
from datetime import datetime

def dump_everything():
    """Dump complete system state for debugging hangs."""
    print(f"\n==== STACK DUMP at {datetime.now().isoformat()} ====")
    
    # Dump all asyncio tasks
    for t in asyncio.all_tasks():
        print(f"\nTASK {t.get_name()}  state={t._state}")
        for f in t.get_stack():
            traceback.print_stack(f, file=sys.stdout)
    
    # Check logging lock
    print("\n==== LOGGING STATE ====")
    print("logging._lock locked?:", logging._lock.locked())
    
    # Check thread pool
    print("\n==== THREAD POOL STATE ====")
    try:
        from mcp_second_brain.utils.thread_pool import get_shared_executor
        pool = get_shared_executor()
        print("thread-pool qsize:", pool._work_queue.qsize())
        print("thread-pool threads alive:", [th.is_alive() for th in pool._threads])
        print("thread-pool threads count:", len(pool._threads))
    except Exception as e:
        print(f"Error checking thread pool: {e}")
    
    # Check all threads
    print("\n==== ALL THREADS ====")
    for thread in threading.enumerate():
        print(f"Thread: {thread.name} (alive={thread.is_alive()}, daemon={thread.daemon})")
    
    sys.stdout.flush()

def schedule_dump(delay=10):
    """Schedule a dump after the specified delay."""
    try:
        loop = asyncio.get_running_loop()
        loop.call_later(delay, dump_everything)
        print(f"Debug dump scheduled in {delay} seconds...")
    except RuntimeError:
        print("No event loop running, cannot schedule dump")