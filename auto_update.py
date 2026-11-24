"""Background release checks; only the UI thread presents an idle-window reminder."""
import queue
import threading
import time

from app_paths import INSTALLED
from update_service import read_release, choose_asset


class AutoUpdateChecker:
    INTERVAL = 6 * 60 * 60
    RETRY = 30 * 60

    def __init__(self, app, notify):
        self.app, self.notify = app, notify
        self.results = queue.Queue()
        self.working = False
        self.next_check = 0
        self.pending = None
        self.notified = set()

    def start(self):
        self.app.root.after(15000, self.tick)

    def fetch(self):
        try:
            release = read_release()
            choose_asset(release, INSTALLED)
            self.results.put((True, release))
        except Exception:
            # Offline startup and GitHub rate limits must not interrupt chat tasks.
            self.results.put((False, None))

    def tick(self):
        app = self.app
        if app.closing:
            return
        now = time.monotonic()
        try:
            ok, value = self.results.get_nowait()
        except queue.Empty:
            pass
        else:
            self.working = False
            self.next_check = now + (self.INTERVAL if ok else self.RETRY)
            if ok:
                self.pending = value if value['newer'] else None
        if not self.working and now >= self.next_check:
            self.working = True
            threading.Thread(target=self.fetch, daemon=True).start()
        existing = getattr(app, '_updates_window', None)
        if (self.pending and self.pending['version'] not in self.notified
                and not app.busy and app.root.state() in ('normal', 'zoomed')
                and app.root.winfo_viewable() and app.root.grab_current() is None
                and not (existing and existing.winfo_exists())):
            release = self.pending
            self.notify(app, release=release)
            self.notified.add(release['version'])
            self.pending = None
        app.root.after(1000, self.tick)


def start_auto_updates(app):
    from update_ui import show_updates
    app.auto_update_checker = AutoUpdateChecker(app, show_updates)
    app.auto_update_checker.start()
