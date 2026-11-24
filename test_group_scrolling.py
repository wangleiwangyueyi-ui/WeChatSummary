"""Large group lists must scroll without embedded child windows or lost selections."""
import importlib.machinery
from pathlib import Path
import time
import unittest
from unittest.mock import patch

import customtkinter as ctk
from tkinter import ttk

gui = importlib.machinery.SourceFileLoader('scroll_test_gui', str(Path(__file__).with_name('wechat_gui.pyw'))).load_module()


class GroupScrollingTests(unittest.TestCase):
    def test_large_list_scroll_search_and_selection(self):
        from secure_store import DEFAULT
        import copy
        cfg = copy.deepcopy(DEFAULT)
        cfg['selected_groups'] = {}
        with patch.object(gui, 'load_config', return_value=cfg), \
             patch.object(gui, 'load_secrets', return_value={}), \
             patch.object(gui.App, 'poll'), patch.object(gui.App, 'tick'):
            root = ctk.CTk()
            try:
                app = gui.App(root)
                root.geometry('1100x740+0+0')
                app.tabs.select('日常汇总')
                groups = {f'{i:04d}@chatroom': f'测试群 {i:04d}' for i in range(815)}
                started = time.perf_counter()
                app.set_groups((groups, {}))
                root.update()
                build_ms = (time.perf_counter()-started)*1000
                listing = app.group_canvas
                self.assertIsInstance(listing, ttk.Treeview)
                self.assertEqual(len(listing.get_children()), 815)
                self.assertEqual(listing.winfo_children(), [])
                first = listing.get_children()[0]
                x, y, w, h = listing.bbox(first)
                listing.event_generate('<Button-1>', x=x+25, y=y+h//2)
                self.assertTrue(app.selected[first].get())
                self.assertEqual(app.selection_count.cget('text'), '已勾选 1 个群')
                # Wheel events must advance exactly one three-row step, not twice.
                listing.event_generate('<MouseWheel>', delta=-120, x=25, y=h//2)
                root.update()
                self.assertAlmostEqual(listing.yview()[0], 3/815, places=5)
                started = time.perf_counter()
                for _ in range(100):
                    listing.yview_scroll(3, 'units')
                    root.update()
                scroll_ms = (time.perf_counter()-started)*1000
                listing.yview_moveto(1)
                root.update()
                self.assertTrue(listing.bbox('0814@chatroom'))
                self.assertTrue(app.selected[first].get())
                app.search.set('测试群 0814')
                app.draw_groups()
                root.update()
                self.assertEqual(listing.get_children(), ('0814@chatroom',))
                self.assertEqual(listing.yview()[0], 0)
                app.search.set('不存在的群')
                app.draw_groups()
                self.assertEqual(listing.get_children(), ('__empty_groups__',))
                app.search.set('')
                app.draw_groups()
                root.update()
                self.assertTrue(app.selected[first].get())
                self.assertEqual(listing.item(first, 'image')[0], str(root._group_check_icons[1]))
                listing.focus(first)
                listing.focus_force()
                root.update()
                listing.event_generate('<space>')
                self.assertFalse(app.selected[first].get())
                print(f'815 groups: load {build_ms:.0f} ms; 100 scroll/redraw steps {scroll_ms:.0f} ms; child windows: 0')
            finally:
                for timer in root.tk.splitlist(root.tk.call('after', 'info')):
                    root.after_cancel(timer)
                root.destroy()


if __name__ == '__main__':
    unittest.main()
