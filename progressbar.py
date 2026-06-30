import threading
import queue
from tqdm import tqdm
from typing import Optional, Callable

class ProgressReporter(threading.Thread):
    def __init__(self, q: queue.Queue):
        super().__init__()
        self.q = q
        self.daemon = True

    def run(self):
        last_stage = None
        bar = None

        while True:
            item = self.q.get()

            if item is None:
                break

            stage, progress, max_val = item

            if stage != last_stage:
                if bar:
                    bar.close()

                print(stage + ":")
                bar = tqdm(total=max_val, dynamic_ncols=True, unit="B", unit_scale=True, unit_divisor=1024)

            if bar:
                bar.n = progress
                bar.refresh()

            last_stage = stage

        if bar:
            bar.close()

class ProgressBar:
    def __init__(self):
        self.progress_q, self.reporter, self.progress_cb = self._make_progress_cb()
    
    def _make_progress_cb(self):
        progress_q = queue.Queue()

        reporter = ProgressReporter(progress_q)
        reporter.start()

        def progress_cb(stage, progress, max_val):
            progress_q.put((stage, progress, max_val))

        return progress_q, reporter, progress_cb
    

class ProgressReport:
    def __init__(self, stage: str, progress: int, max_val: int):
        self.stage = stage
        self.progress = progress
        self.max = max_val


def report_progress(callback: Optional[Callable], stage, progress, max_val):
    if callback:
        callback(stage, progress, max_val)