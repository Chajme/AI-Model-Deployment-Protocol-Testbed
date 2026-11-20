import threading
import time
import psutil
import os

class ResourceMonitor:
    """
    Samples CPU % and RSS memory in a background thread.
    Energy is estimated from average CPU load × system TDP.

    Usage:
        monitor = ResourceMonitor(sample_interval=0.05)
        monitor.start()
        # ... do work ...
        stats = monitor.stop()

    stop() keeps sampling until at least MIN_WINDOW_SECONDS have elapsed
    since start(): fast transfers (tens of milliseconds) would otherwise
    collect zero or one sample and report 0% CPU / 0 J (ISSUES.md OPEN-2).
    The returned `sample_count` records how many samples back the averages;
    rows with very few samples should be treated as low-confidence.
    stop() is idempotent — later calls return the same stats.
    """

    # Conservative default TDP in watts — override with your actual CPU TDP.
    # On Linux you can read: /sys/class/powercap/intel-rapl/intel-rapl:0/constraint_0_power_limit_uw
    DEFAULT_TDP_WATTS = float(os.environ.get("CPU_TDP_WATTS", 15.0))

    # Minimum sampling window so short transfers still yield usable averages.
    MIN_WINDOW_SECONDS = 0.2

    def __init__(self, sample_interval: float = 0.05):
        self.sample_interval = sample_interval
        self._cpu_samples: list[float] = []
        self._rss_samples: list[int] = []
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._start_time: float = 0.0
        self._end_time: float = 0.0
        self._stats: dict | None = None

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
        self._stats = None
        self._thread = threading.Thread(target=self._sample_loop, daemon=True)
        self._thread.start()

    def stop(self, min_window: float | None = None) -> dict:
        # Idempotent: a second stop() (e.g. in a finally block) returns the
        # stats already computed by the first one.
        if self._stats is not None:
            return self._stats

        # Keep sampling until the minimum window has elapsed so short
        # transfers still collect a handful of samples (OPEN-2).
        if min_window is None:
            min_window = self.MIN_WINDOW_SECONDS
        remaining = min_window - (time.perf_counter() - self._start_time)
        if remaining > 0:
            time.sleep(remaining)

        self._stop_event.set()
        self._end_time = time.perf_counter()
        if self._thread:
            self._thread.join(timeout=2)

        duration_s = self._end_time - self._start_time

        avg_cpu_pct  = sum(self._cpu_samples) / len(self._cpu_samples) if self._cpu_samples else 0.0
        avg_cpu_pct = avg_cpu_pct / (self.cpu_count or 1)
        peak_rss_mb  = max(self._rss_samples) / (1024 ** 2) if self._rss_samples else 0.0

        # avg_cpu_pct is already normalised to a single core (0-100) above,
        # so turn it straight into a 0-1 fraction of one core, then multiply
        # by TDP and duration for a joule estimate. Dividing by the core count
        # again here would under-report energy by ~num_cores.
        # This is an approximation — RAPL (see Option 2) is more accurate.
        cpu_fraction  = avg_cpu_pct / 100.0
        energy_j      = cpu_fraction * self.DEFAULT_TDP_WATTS * duration_s

        self._stats = {
            "avg_cpu_pct":   round(avg_cpu_pct, 3),
            "peak_rss_mb":   round(peak_rss_mb, 3),
            "energy_j":      round(energy_j, 6),
            "sample_count":  len(self._cpu_samples),
        }
        return self._stats