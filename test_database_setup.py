"""Exercise the app entry point without reading WeChat memory or real secrets."""
import copy
import importlib.machinery
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import customtkinter as ctk
import database_key_setup as setup
import secure_store

ROOT = Path(__file__).resolve().parent
gui = importlib.machinery.SourceFileLoader('database_setup_gui', str(ROOT / 'wechat_gui.pyw')).load_module()


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        for name in setup.REQUIRED_FILES:
            file = self.folder / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text('')
        self.path_patch = patch.object(setup, 'APP_DIR', self.folder)
        self.path_patch.start()
        self.app = SimpleNamespace(busy=False, closing=False, root=Mock(),
                                   save_base=Mock(return_value=True), cfg={'wechat_dir': 'test-account'},
                                   status=Mock(), key_status=Mock())

    def tearDown(self):
        self.path_patch.stop()
        self.tmp.cleanup()

    def test_normal_app_entry_launch_and_reload(self):
        process = Mock()
        process.poll.return_value = None
        with patch.object(setup.subprocess, 'Popen', return_value=process) as launch:
            gui.App.open_wizard(self.app)
            self.assertEqual(Path(launch.call_args.args[0][0]).name, 'pythonw.exe')
            self.assertEqual(launch.call_args.args[0][1], str(self.folder / 'initialize_offline.pyw'))
            self.assertIs(self.app.database_setup_process, process)
            callback = self.app.root.after.call_args.args[1]
            callback()
            process.poll.return_value = 0
            with patch.object(setup, 'load_secrets', return_value={'db_keys': {'test-salt': 'test-key'}}):
                callback()
            self.app.key_status.set.assert_called_with('本机已保存数据库密钥：1 个')

    def test_busy_duplicate_missing_and_failed_save_do_not_launch(self):
        with patch.object(setup, 'messagebox'), patch.object(setup.subprocess, 'Popen') as launch:
            self.app.busy = True
            setup.open_setup(self.app)
            self.app.busy = False
            self.app.database_setup_process = Mock()
            self.app.database_setup_process.poll.return_value = None
            setup.open_setup(self.app)
            self.app.database_setup_process = None
            self.app.save_base.return_value = False
            setup.open_setup(self.app)
            self.app.save_base.return_value = True
            (self.folder / 'bootstrap/key.py').unlink()
            setup.open_setup(self.app)
            launch.assert_not_called()

    def test_launch_failure_is_reported(self):
        with patch.object(setup.subprocess, 'Popen', side_effect=OSError('test launch failure')), \
                patch.object(setup, 'messagebox') as dialogs:
            setup.open_setup(self.app)
            dialogs.showerror.assert_called_once()

    def test_configuration_button_invokes_setup_and_preserves_backup_import(self):
        cfg = copy.deepcopy(secure_store.DEFAULT)
        with patch.object(gui, 'load_config', return_value=cfg), \
                patch.object(gui, 'load_secrets', return_value={}), \
                patch.object(gui, 'Scheduler'), \
                patch.object(gui.App, 'tick'), patch.object(gui.App, 'poll'), \
                patch.object(setup, 'open_setup') as entry:
            root = ctk.CTk()
            root.withdraw()
            try:
                app = gui.App(root)
                button = app.ui_controls['open_wizard']
                self.assertEqual(button.cget('text'), '提取数据库密钥')
                button.invoke()
                entry.assert_called_once_with(app)
                self.assertIn('import_export_keys', app.ui_controls)
            finally:
                for timer in root.tk.splitlist(root.tk.call('after', 'info')):
                    root.after_cancel(timer)
                root.destroy()

    def test_release_includes_wizard_and_extractor_sources(self):
        from release_tools.prepare_release import PROGRAM, BOOTSTRAP
        self.assertIn('initialize_offline.pyw', PROGRAM)
        self.assertIn('database_key_setup.py', PROGRAM)
        for name in setup.REQUIRED_FILES[1:]:
            self.assertIn(name, BOOTSTRAP)


if __name__ == '__main__':
    unittest.main(verbosity=2)
