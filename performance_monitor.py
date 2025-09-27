# performance_monitor.py
import time
import psutil
from contextlib import contextmanager
from typing import Dict, Any
import threading

class PerformanceMonitor:
    def __init__(self):
        self.metrics = {}
        self._start_times = {}
        
    @contextmanager
    def measure_operation(self, operation_name: str):
        """Context manager to measure operation performance"""
        start_time = time.time()
        start_memory = psutil.virtual_memory().percent
        start_cpu = psutil.cpu_percent()
        
        try:
            yield
        finally:
            end_time = time.time()
            end_memory = psutil.virtual_memory().percent
            end_cpu = psutil.cpu_percent()
            
            self.metrics[operation_name] = {
                'duration_seconds': end_time - start_time,
                'memory_start_percent': start_memory,
                'memory_end_percent': end_memory,
                'memory_delta_percent': end_memory - start_memory,
                'cpu_start_percent': start_cpu,
                'cpu_end_percent': end_cpu,
                'timestamp': time.time()
            }
    
    def start_timer(self, operation_name: str):
        """Start timing an operation"""
        self._start_times[operation_name] = time.time()
    
    def end_timer(self, operation_name: str):
        """End timing an operation"""
        if operation_name in self._start_times:
            duration = time.time() - self._start_times[operation_name]
            self.metrics[operation_name] = {
                'duration_seconds': duration,
                'timestamp': time.time()
            }
            del self._start_times[operation_name]
    
    def get_system_info(self) -> Dict[str, Any]:
        """Get current system performance info"""
        return {
            'cpu_percent': psutil.cpu_percent(interval=1),
            'memory_percent': psutil.virtual_memory().percent,
            'disk_usage_percent': psutil.disk_usage('/').percent,
            'available_memory_gb': psutil.virtual_memory().available / (1024**3)
        }
    
    def get_performance_report(self) -> Dict[str, Any]:
        """Generate performance report"""
        return {
            'system_info': self.get_system_info(),
            'operation_metrics': self.metrics,
            'total_operations': len(self.metrics)
        }