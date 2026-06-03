"""
core/progress_tracker.py — Progress display (event bus or heartbeat)
"""
import time
import threading

def make_tracker(unit: str):
    try:
        from crewai.utilities.events import crewai_event_bus
        from crewai.utilities.events.task_events import TaskStartedEvent, TaskCompletedEvent
        from crewai.utilities.events.crew_events import CrewStartedEvent

        class _EventTracker:
            def __init__(self):
                self.total = 0; self.done = 0
                self.current = "initialising"
                self.start_time = time.time()
                crewai_event_bus.on(CrewStartedEvent)(self._on_crew)
                crewai_event_bus.on(TaskStartedEvent)(self._on_task_start)
                crewai_event_bus.on(TaskCompletedEvent)(self._on_task_done)
            def _on_crew(self, src, event): self.total = len(event.crew.tasks)
            def _on_task_start(self, src, event):
                self.current = getattr(event.task, "name", "…"); self._render()
            def _on_task_done(self, src, event):
                self.done += 1; self._render()
            def _render(self):
                elapsed = time.time() - self.start_time
                pct = int(self.done / self.total * 100) if self.total else 0
                bar = ("█" * (pct // 5)).ljust(20, "░")
                eta_str = f"  ETA {int((elapsed/self.done)*(self.total-self.done))}s" if self.done > 0 and self.total > 0 else ""
                print(f"\r  [{bar}] {pct:3d}%  {self.done}/{self.total} tasks  ⏱ {int(elapsed)}s{eta_str}  → {self.current[:35].ljust(35)}", end="", flush=True)
            def stop(self):
                try:
                    crewai_event_bus.off(CrewStartedEvent, self._on_crew)
                    crewai_event_bus.off(TaskStartedEvent, self._on_task_start)
                    crewai_event_bus.off(TaskCompletedEvent, self._on_task_done)
                except Exception: pass
                print("\r" + " " * 90 + "\r", end="", flush=True)
        return _EventTracker()
    except Exception:
        class _HeartbeatTracker:
            def __init__(self):
                self._stop = threading.Event(); self._start = time.time()
                self._thread = threading.Thread(target=self._beat, daemon=True)
                self._thread.start()
            def _beat(self):
                spinners = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]; step = 0
                while not self._stop.is_set():
                    self._stop.wait(10)
                    if not self._stop.is_set():
                        elapsed = int(time.time() - self._start); m, s = divmod(elapsed, 60)
                        print(f"  {spinners[step%len(spinners)]}  {unit}  {m:02d}:{s:02d} elapsed ...", flush=True); step += 1
            def stop(self):
                self._stop.set(); self._thread.join(timeout=1)
        return _HeartbeatTracker()
