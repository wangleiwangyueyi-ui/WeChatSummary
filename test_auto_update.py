import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import auto_update


class AutomaticUpdateTests(unittest.TestCase):
    def setUp(self):
        self.root = Mock()
        self.root.state.return_value = 'normal'
        self.root.winfo_viewable.return_value = True
        self.root.grab_current.return_value = None
        self.app = SimpleNamespace(root=self.root, closing=False, busy=False)
        self.notify = Mock()
        self.checker = auto_update.AutoUpdateChecker(self.app, self.notify)
        self.checker.next_check = float('inf')
        self.release = {'version':'99.0.0','newer':True}

    def test_startup_delay_and_worker_without_ui_blocking(self):
        self.checker.start()
        self.assertEqual(self.root.after.call_args.args[0], 15000)
        self.checker.next_check = 0
        with patch.object(auto_update.threading, 'Thread') as thread:
            self.checker.tick()
            self.checker.tick()
            thread.assert_called_once_with(target=self.checker.fetch, daemon=True)
            thread.return_value.start.assert_called_once()
        self.notify.assert_not_called()

    def test_busy_hidden_modal_and_existing_window_defer_reminder(self):
        self.checker.results.put((True,self.release))
        self.app.busy = True
        self.checker.tick()
        self.app.busy = False
        self.root.state.return_value = 'withdrawn'
        self.checker.tick()
        self.root.state.return_value = 'normal'
        self.root.grab_current.return_value = object()
        self.checker.tick()
        self.root.grab_current.return_value = None
        self.app._updates_window = Mock()
        self.checker.tick()
        self.notify.assert_not_called()
        self.app._updates_window = None
        self.root.state.return_value = 'zoomed'
        self.checker.tick()
        self.notify.assert_called_once_with(self.app,release=self.release)

    def test_each_version_only_once_and_no_current_version_popup(self):
        for _ in range(2):
            self.checker.results.put((True,self.release))
            self.checker.tick()
        self.notify.assert_called_once()
        self.checker.results.put((True,{'version':'99.0.1','newer':True}))
        self.checker.tick()
        self.assertEqual(self.notify.call_count,2)
        self.checker.results.put((True,{'version':'1.0.0','newer':False}))
        self.checker.tick()
        self.assertEqual(self.notify.call_count,2)

    def test_errors_retry_quietly_success_waits_six_hours_and_exit_stops(self):
        with patch.object(auto_update,'read_release',side_effect=OSError('offline')):
            self.checker.fetch()
        with patch.object(auto_update.time,'monotonic',return_value=100):
            self.checker.tick()
            self.assertEqual(self.checker.next_check,1900)
            self.notify.assert_not_called()
            self.checker.results.put((True,{'version':'1.0.0','newer':False}))
            self.checker.tick()
            self.assertEqual(self.checker.next_check,21700)
        self.app.closing=True
        self.root.after.reset_mock()
        self.checker.tick()
        self.root.after.assert_not_called()

    def test_fetch_validates_package_before_notifying(self):
        with patch.object(auto_update,'read_release',return_value=self.release), \
             patch.object(auto_update,'choose_asset',side_effect=ValueError('bad manifest')):
            self.checker.fetch()
        self.checker.tick()
        self.notify.assert_not_called()


if __name__ == '__main__':
    unittest.main()
