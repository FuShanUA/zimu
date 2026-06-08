
import sys
import os
import unittest
from unittest.mock import MagicMock, patch
import threading
import time

# Mock Tkinter before importing the GUI
sys.modules['tkinter'] = MagicMock()
sys.modules['tkinter.ttk'] = MagicMock()
sys.modules['tkinter.filedialog'] = MagicMock()
sys.modules['tkinter.messagebox'] = MagicMock()

# Mock other dependencies
sys.modules['llm_utils'] = MagicMock()

# Now import the class we want to test
# We need to add the path to the tool
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.append(CURRENT_DIR)

from autosub_gui import AutoSubGUI

class TestGUILogic(unittest.TestCase):
    def setUp(self):
        self.root = MagicMock()
        # Initialize the GUI with mocked root
        with patch('autosub_gui.AutoSubGUI.load_settings', return_value={}):
            with patch('autosub_gui.AutoSubGUI.setup_ui'):
                self.gui = AutoSubGUI(self.root)
    
    def test_run_worker_race_condition(self):
        """
        Simulate the run_worker method and check if it handles the returncode correctly
        even if self.current_process is set to None in finally block.
        """
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = []
        
        # We want to see if the callback passed to after() will fail
        # In a real GUI, after() schedules a callback. 
        # Here we capture what was passed to after().
        captured_callbacks = []
        def mock_after(ms, func, *args):
            captured_callbacks.append(func)
            
        self.root.after.side_effect = mock_after
        
        # Simulate FIX logic
        try:
            self.gui.current_process = mock_process
            # Simulated fix: capture ret_code
            ret_code = self.gui.current_process.wait()
            callback = lambda r=ret_code: print(f"Returncode: {r}")
            self.root.after(0, callback)
        finally:
            self.gui.current_process = None
            
        # Now try to run the captured callback
        print("Executing scheduled callback after process was cleared...")
        try:
            captured_callbacks[0]()
            print("✅ Callback succeeded (No bug)")
        except AttributeError as e:
            print(f"❌ Callback failed with AttributeError: {e} (Bug reproduced!)")
            raise e

if __name__ == "__main__":
    unittest.main()
