"""Offline regression checks using synthetic participants and temporary UI state."""
import hashlib
from pathlib import Path
from types import SimpleNamespace
import sqlite3
import threading
import unittest
from unittest.mock import patch

import customtkinter as ctk
from tkinter import ttk, StringVar
import history_selectors as selectors
from message_parser import match_name


class ParticipantTests(unittest.TestCase):
    def test_exact_identity_does_not_match_another_person_nickname(self):
        self.assertTrue(match_name('id=alice', 'Alice', ('alice', 'A')))
        self.assertFalse(match_name('id=alice', 'Bob', ('bob', 'alice')))
        self.assertTrue(match_name('ali', 'Alice', ('alice',)))

    def test_unique_speakers_and_incomplete_shard(self):
        connection = sqlite3.connect(':memory:')
        self.addCleanup(connection.close)
        table = 'Msg_' + hashlib.md5(b'room').hexdigest()
        connection.execute('CREATE TABLE Name2Id (user_name TEXT)')
        connection.executemany('INSERT INTO Name2Id VALUES (?)', [('alice',), ('bob',)])
        connection.execute(f'CREATE TABLE {table} (real_sender_id INTEGER)')
        connection.executemany(f'INSERT INTO {table} VALUES (?)', [(1,), (1,), (2,)])
        people = {'alice': {'nick_name': None, 'remark': None}, 'bob': {'nick_name': 'Bob'}}
        with patch.object(selectors, 'contacts', return_value=people), \
             patch.object(selectors, 'storage', return_value=Path('.')), \
             patch.object(selectors, 'message_sources', return_value=[Path('message_0.db'), Path('message_1.db')]), \
             patch.object(selectors, 'snapshot', side_effect=[connection, sqlite3.DatabaseError('synthetic invalid shard')]):
            rows, missing = selectors.history_participants({}, {}, 'room', threading.Event())
        self.assertEqual({row[0] for row in rows}, {'alice', 'bob'})
        self.assertTrue(all(isinstance(value, str) for row in rows for value in row))
        self.assertEqual(missing, ['message_1.db'])


class CalendarTests(unittest.TestCase):
    def test_participant_dialog_selects_exact_user(self):
        root = ctk.CTk()
        root.withdraw()
        self.addCleanup(root.destroy)
        person = StringVar(root)
        app = SimpleNamespace(root=root, busy=False, group_choice=StringVar(root, value='Test | room'),
                              cfg={}, secrets={}, offline_export_keys=None, person=person)
        with patch.object(selectors, 'reveal'), \
             patch.object(selectors, 'history_participants', return_value=([('alice', 'Alice', 'A', '')], [])):
            window = selectors.participant_dialog(app)
            root.after(250, root.quit)
            root.mainloop()
        listing = next(w for w in window.winfo_children() if isinstance(w, ttk.Treeview))
        listing.selection_set('alice')
        controls = [w for frame in window.winfo_children() for w in frame.winfo_children()]
        next(w for w in controls if isinstance(w, ctk.CTkButton) and w.cget('text') == '选择此人').invoke()
        self.assertEqual(person.get(), 'id=alice')

    def test_year_change_clamps_leap_day_and_preserves_time(self):
        root = ctk.CTk()
        root.withdraw()
        self.addCleanup(root.destroy)
        value = StringVar(root, value='2024-02-29 23:59')
        with patch.object(selectors, 'reveal'):
            window = selectors.calendar_dialog(root, value, 'Test date')
        def children(widget):
            for child in widget.winfo_children():
                yield child
                yield from children(child)
        fields = [w for w in children(window) if isinstance(w, ttk.Spinbox)]
        window.setvar(str(fields[0].cget('textvariable')), '2023')
        fields[0].event_generate('<FocusOut>')
        confirm = next(w for w in children(window) if isinstance(w, ctk.CTkButton) and w.cget('text') == '确定')
        confirm.invoke()
        self.assertEqual(value.get(), '2023-02-28 23:59')


if __name__ == '__main__':
    unittest.main()
