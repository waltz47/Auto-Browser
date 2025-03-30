import time
import functools
import cProfile
import pstats
import io
from typing import Callable, Any
import asyncio
from contextlib import contextmanager
import threading

# Thread-local storage to track active profilers
_local = threading.local()
_local.active_profiler = False

class Timer:
    def __init__(self, name: str):
        self.name = name
        
    async def __aenter__(self):
        self.start = time.time()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        end = time.time()
        print(f"[TIMER] {self.name}: {end - self.start:.4f}s")

def async_profile(func: Callable) -> Callable:
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        # Check if a profiler is already active
        if getattr(_local, 'active_profiler', False):
            # If active, just run the function without profiling
            return await func(*args, **kwargs)
        
        try:
            # Set profiler as active
            _local.active_profiler = True
            
            pr = cProfile.Profile()
            pr.enable()
            
            start_time = time.time()
            result = await func(*args, **kwargs)
            end_time = time.time()
            
            pr.disable()
            s = io.StringIO()
            ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
            ps.print_stats(20)  # Print top 20 time-consuming operations
            
            print(f"\n[PROFILE] Function {func.__name__}")
            print(f"[PROFILE] Total time: {end_time - start_time:.4f}s")
            print(f"[PROFILE] Detailed stats:\n{s.getvalue()}")
            
            return result
        finally:
            # Always reset the profiler state
            _local.active_profiler = False
            
    return wrapper 