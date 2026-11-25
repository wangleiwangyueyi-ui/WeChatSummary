"""Synthetic keys only: no WeChat process reads, network changes or log deletion."""
import importlib.machinery
from pathlib import Path
import queue
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).parent
wizard = importlib.machinery.SourceFileLoader('unified_key_test', str(ROOT/'initialize_offline.pyw')).load_module()
images = importlib.machinery.SourceFileLoader('image_key_test', str(ROOT/'initialize_images.pyw')).load_module()


class UnifiedKeysTests(unittest.TestCase):
    def instance(self):
        obj = wizard.Wizard.__new__(wizard.Wizard)
        obj.events = queue.Queue()
        return obj

    def test_combined_runs_in_order_and_retains_success_when_other_fails(self):
        obj = self.instance()
        calls=[]
        obj.extract = Mock(side_effect=lambda:calls.append('database'))
        obj.extract_images = Mock(side_effect=lambda:calls.append('image'))
        with patch.object(wizard,'require_offline'):
            obj.extract_both()
        self.assertEqual(calls,['database','image'])
        obj.extract.side_effect=ValueError('synthetic database failure')
        obj.extract_images.reset_mock()
        with patch.object(wizard,'require_offline'),self.assertRaisesRegex(RuntimeError,'已成功的结果已单独保存'):
            obj.extract_both()
        obj.extract_images.assert_called_once()

    def test_reconnection_stops_next_extraction(self):
        obj=self.instance()
        obj.extract, obj.extract_images=Mock(),Mock()
        with patch.object(wizard,'require_offline',side_effect=[None,RuntimeError('online')]),self.assertRaisesRegex(RuntimeError,'online'):
            obj.extract_both()
        obj.extract.assert_called_once()
        obj.extract_images.assert_not_called()

    def test_image_success_preserves_database_credentials_and_zero_xor(self):
        obj=self.instance()
        module=Mock()
        module.extract.return_value=('ab'*16,0,2)
        obj.module=Mock(return_value=module)
        saved={'db_keys':{'salt':'synthetic'},'gemini_api_key':'synthetic-api'}
        with tempfile.TemporaryDirectory() as tmp,patch.object(images,'BASE',Path(tmp)), \
             patch.object(images,'load_config',return_value={'wechat_dir':'test','enabled':False}), \
             patch.object(images,'load_secrets',return_value=saved),patch.object(images,'save_secrets') as save:
            images.ImageWizard.extract(obj)
            result=save.call_args.args[0]
            self.assertEqual(result['db_keys'],{'salt':'synthetic'})
            self.assertEqual(result['image_xor_key'],0)
            self.assertEqual(result['image_key_hex'],'ab'*16)
            receipt=(Path(tmp)/'image_initialization_status.json').read_text()
            self.assertNotIn('ab'*16,receipt)
        self.assertNotIn('ab'*16,' '.join(list(obj.events.queue)))

    def test_wizard_does_not_extract_on_open(self):
        import tkinter as tk
        root=tk.Tk()
        root.withdraw()
        try:
            with patch.object(wizard,'load_secrets',return_value={}),patch.object(wizard,'image_wizard_class') as helper:
                obj=wizard.Wizard(root)
                self.assertIn('数据库与图片',root.title())
                self.assertIn('图片密钥：未保存',obj.key_state.get())
                helper.assert_not_called()
        finally:
            for timer in root.tk.splitlist(root.tk.call('after','info')):root.after_cancel(timer)
            root.destroy()

    def test_running_wechat_prevents_all_cleanup(self):
        obj=self.instance()
        with patch.object(wizard,'ps',return_value='1'),patch.object(wizard,'image_wizard_class') as helper, \
             patch.object(wizard.subprocess,'run') as run,self.assertRaisesRegex(RuntimeError,'退出微信'):
            obj.cleanup()
        helper.assert_not_called()
        run.assert_not_called()


if __name__=='__main__':unittest.main()
