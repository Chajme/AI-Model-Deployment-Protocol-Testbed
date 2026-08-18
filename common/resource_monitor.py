import threading
import time
import psutil
import os

class ResourceMonitor:
    """
    Samples CPU % and RSS memory in a background thread.
    Energy is estimated from average CPU load × system TDP.

    Usage:
        monitor = ResourceMonitor(sample_interval=0.1)
        monitor.start()
        # ... do work ...
        stats = monitor.stop()
    """

    # Conservative default TDP in watts — override with your actual CPU TDP.
    # On Linux you can read: /sys/class/powercap/intel-rapl/intel-rapl:0/constraint_0_power_limit_uw
    DEFAULT_TDP_WATTS = float(os.environ.get("CPU_TDP_WATTS", 15.0))

    def __init__(self, sample_interval: float = 0.05):
        self.sample_interval = sample_interval
        self._cpu_samples: list[float] = []
        self._rss_samples: list[int] = []
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._start_time: float = 0.0
        self._end_time: float = 0.0

        # Use the whole process tree (client + any subprocesses)
        self._proc = psutil.Process(os.getpid())
        self.cpu_count =  psutil.cpu_count()

    def _sample_loop(self):
        # Warm up the CPU percent counter (first call always returns 0.0)
        self._proc.cpu_percent(interval=None)

        while not self._stop_event.is_set():
            try:
                cpu = self._proc.cpu_percent(interval=None) # non-blocking
                rss = self._proc.memory_info().rss            # bytes
                self._cpu_samples.append(cpu)
                self._rss_samples.append(rss)
            except psutil.NoSuchProcess:
                break
            time.sleep(self.sample_interval)

    def start(self):
        self._cpu_samples.clear()
        self._rss_samples.clear()
        self._stop_event.clear()
        self._start_time = time.perf_counter()
        self._thread = threading.Thread(target=self._sample_loop, daemon=True)
        self._thread.start()

    def stop(self) -> dict:
        self._stop_event.set()
        self._end_time = time.perf_counter()
        if self._thread:
            self._thread.join(timeout=2)

        duration_s = self._end_time - self._start_time

        avg_cpu_pct  = sum(self._cpu_samples) / len(self._cpu_samples) if self._cpu_samples else 0.0
        avg_cpu_pct = avg_cpu_pct / (self.cpu_count or 1)
        peak_rss_mb  = max(self._rss_samples) / (1024 ** 2) if self._rss_samples else 0.0

        # Normalise CPU % to a 0-1 fraction of one core,
        # then multiply by TDP and duration for a joule estimate.
        # This is an approximation — RAPL (see Option 2) is more accurate.
        num_cores     = psutil.cpu_count(logical=True) or 1
        cpu_fraction  = (avg_cpu_pct / 100.0) / num_cores
        energy_j      = cpu_fraction * self.DEFAULT_TDP_WATTS * duration_s

        return {
            "avg_cpu_pct":   round(avg_cpu_pct, 3),
            "peak_rss_mb":   round(peak_rss_mb, 3),
            "energy_j":      round(energy_j, 6),
            "sample_count":  len(self._cpu_samples),
        }