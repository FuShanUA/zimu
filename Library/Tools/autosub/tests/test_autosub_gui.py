import os
import sys
import unittest
from unittest.mock import MagicMock, patch, call
import time

# Add current dir to path to import autosub modules
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

import tkinter as tk
from autosub_terminal_gui import TerminalGUI

class DummyEvent:
    def __init__(self, char="", keysym="", widget=None):
        self.char = char
        self.keysym = keysym
        self.widget = widget

class TestTerminalGUI(unittest.TestCase):

    @patch("subprocess.Popen")
    def setUp(self, mock_popen):
        self.root = tk.Tk()
        self.root.withdraw()
        
        self.mock_proc = MagicMock()
        self.mock_proc.poll.return_value = None
        self.mock_proc.stdin = MagicMock()
        mock_popen.return_value = self.mock_proc

        self.gui = TerminalGUI(self.root, ["python3", "dummy.py"])

    def tearDown(self):
        self.root.destroy()

    def test_entry_return_sends_chars_and_cr(self):
        """Pressing Enter in the entry should send each char + LF to child stdin."""
        self.gui.input_entry.insert(0, "q")
        self.gui.on_entry_return(DummyEvent(keysym="Return"))
        
        # Give background threads time to execute
        time.sleep(0.2)
        
        # Should have sent 'q' then '\n'
        calls = self.gui.proc.stdin.write.call_args_list
        written = b"".join(c[0][0] for c in calls)
        self.assertIn(b"q", written)
        self.assertIn(b"\n", written)
        
        # Entry should be cleared
        self.assertEqual(self.gui.input_entry.get(), "")

    def test_arrow_up_sends_escape_sequence(self):
        """Arrow Up should send ESC[A to child stdin for pagination."""
        self.gui.on_global_key(DummyEvent(keysym="Up"))
        time.sleep(0.2)
        
        self.gui.proc.stdin.write.assert_called_with(b'\x1b[A')

    def test_arrow_down_sends_escape_sequence(self):
        """Arrow Down should send ESC[B to child stdin for pagination."""
        self.gui.on_global_key(DummyEvent(keysym="Down"))
        time.sleep(0.2)
        
        self.gui.proc.stdin.write.assert_called_with(b'\x1b[B')

    def test_text_area_is_readonly(self):
        """The text_area should be in disabled (read-only) state."""
        self.assertEqual(str(self.gui.text_area.cget("state")), "disabled")

    def test_empty_enter_sends_newline(self):
        """Pressing Enter with empty entry should send \\n for launcher prompts."""
        self.gui.input_entry.delete(0, "end")
        self.gui.on_entry_return(DummyEvent(keysym="Return"))
        time.sleep(0.2)
        
        self.gui.proc.stdin.write.assert_called_with(b'\n')

if __name__ == "__main__":
    unittest.main()
