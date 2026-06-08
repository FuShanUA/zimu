import os
import sys
import json
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Add current dir to path to import autosub modules
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

# Import the targeted functions/classes
import autosub_launcher
from autosub_batch_pro import BatchEngine, SubTask, ResourceManager

class TestAutoSubStateAndLauncher(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_parse_indices_empty(self):
        """Empty inputs should keep all indices."""
        res = autosub_launcher.parse_indices("", 10)
        self.assertEqual(res, set(range(1, 11)))

    def test_parse_indices_exclusion(self):
        """Standard input list should exclude specified indices."""
        res = autosub_launcher.parse_indices("1,3,5", 5)
        self.assertEqual(res, {2, 4})

    def test_parse_indices_inclusion(self):
        """Input list prefixed with '+' or 'i'/'I' should only keep specified indices."""
        res1 = autosub_launcher.parse_indices("+2,4", 5)
        self.assertEqual(res1, {2, 4})
        res2 = autosub_launcher.parse_indices("i1,3", 5)
        self.assertEqual(res2, {1, 3})

    def test_parse_indices_ranges(self):
        """Range patterns (e.g. 1-3) should be parsed correctly."""
        res1 = autosub_launcher.parse_indices("1-3", 5)  # Exclusion of 1,2,3 -> keep 4,5
        self.assertEqual(res1, {4, 5})
        res2 = autosub_launcher.parse_indices("+2-4", 5)  # Inclusion of 2,3,4 -> keep 2,3,4
        self.assertEqual(res2, {2, 3, 4})

    @patch("subprocess.Popen")
    def test_fetch_metadata_anonymous(self, mock_popen):
        """Anonymous metadata fetch should build the command and run subprocess."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b'{"id": "123", "title": "Test Vid"}', b'')
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        data = autosub_launcher.fetch_metadata("http://test-url.com")
        self.assertIsNotNone(data)
        self.assertEqual(data.get("id"), "123")
        self.assertEqual(data.get("title"), "Test Vid")

    @patch("subprocess.Popen")
    def test_fetch_metadata_with_browser(self, mock_popen):
        """Browser cookies fetch should add --cookies-from-browser option and execute command."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b'{"id": "456", "title": "Browser Vid"}', b'')
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        data = autosub_launcher.fetch_metadata("http://test-url.com", browser="chrome")
        self.assertIsNotNone(data)
        self.assertEqual(data.get("id"), "456")

        # Verify command argument contains chrome cookies
        args, kwargs = mock_popen.call_args
        cmd = args[0]
        self.assertIn("--cookies-from-browser", cmd)
        self.assertIn("chrome", cmd)

    @patch("subprocess.Popen")
    @patch("autosub_launcher.use_temp_cookies")
    def test_fetch_metadata_with_cookies(self, mock_temp_cookies, mock_popen):
        """Cookies.txt path fetch should copy cookies to temp file and run inside context manager."""
        mock_temp_cookies.return_value.__enter__.return_value = "/tmp/fake_temp_cookies.txt"
        
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b'{"id": "789", "title": "Cookies Vid"}', b'')
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        data = autosub_launcher.fetch_metadata("http://test-url.com", cookies_path="/path/to/cookies.txt")
        self.assertIsNotNone(data)
        self.assertEqual(data.get("id"), "789")

        # Verify command argument contains temp cookies file
        args, kwargs = mock_popen.call_args
        cmd = args[0]
        self.assertIn("--cookies", cmd)
        self.assertIn("/tmp/fake_temp_cookies.txt", cmd)

    def test_disk_truth_fully_completed(self):
        """If workdir contains _hardsub.mp4 and .burn_complete, disk_truth should set status to Completed."""
        task = SubTask(
            uid=1,
            url="http://test.com",
            title="Video 1",
            vid_id="vid1",
            workdir=os.path.join(self.temp_dir, "task_1"),
            pcts={"DL": 0.0, "TR": 0.0, "TL": 0.0, "MR": 0.0, "BR": 0.0, "GD": 0.0}
        )
        os.makedirs(task.workdir)
        
        # Create completed files
        with open(os.path.join(task.workdir, "video1_hardsub.mp4"), "w") as f:
            f.write("A" * 2 * 1024 * 1024)  # 2MB file
        with open(os.path.join(task.workdir, ".burn_complete"), "w") as f:
            f.write("1")

        engine = BatchEngine(output_dir=self.temp_dir, sub_dir_name="project_1")
        engine.disk_truth(task)

        self.assertEqual(task.status, "完成")
        for stage, val in task.pcts.items():
            self.assertEqual(val, 100.0)

    def test_disk_truth_missing_burn_complete_auto_repair(self):
        """If workdir contains _hardsub.mp4 (>1MB) but lacks .burn_complete, it should auto-repair and set status to Completed."""
        task = SubTask(
            uid=2,
            url="http://test.com",
            title="Video 2",
            vid_id="vid2",
            workdir=os.path.join(self.temp_dir, "task_2"),
            pcts={"DL": 0.0, "TR": 0.0, "TL": 0.0, "MR": 0.0, "BR": 0.0, "GD": 0.0}
        )
        os.makedirs(task.workdir)
        
        # Create completed hardsub video but NO .burn_complete
        with open(os.path.join(task.workdir, "video2_hardsub.mp4"), "w") as f:
            f.write("A" * 2 * 1024 * 1024)  # 2MB file

        engine = BatchEngine(output_dir=self.temp_dir, sub_dir_name="project_1")
        engine.disk_truth(task)

        # It should have auto-created .burn_complete
        self.assertTrue(os.path.exists(os.path.join(task.workdir, ".burn_complete")))
        self.assertEqual(task.status, "完成")
        for stage, val in task.pcts.items():
            self.assertEqual(val, 100.0)

    def test_check_all_completed_empty(self):
        """None or empty state should return False."""
        self.assertFalse(autosub_launcher.check_all_completed(None))
        self.assertFalse(autosub_launcher.check_all_completed({}))

    def test_check_all_completed_launcher_format(self):
        """Launcher format (direct dict map) with all completed should return True."""
        state = {
            "1": {"status": "完成", "pcts": {"DL": 100.0, "TR": 100.0, "BR": 100.0}},
            "2": {"status": "压制中", "pcts": {"DL": 100.0, "TR": 100.0, "BR": 100.0}},  # BR >= 100.0 is also completed!
        }
        self.assertTrue(autosub_launcher.check_all_completed(state))

    def test_check_all_completed_pro_format(self):
        """Pro format (nested tasks key) with some incomplete should return False."""
        state = {
            "tasks": {
                "1": {"status": "完成", "pcts": {"DL": 100.0, "TR": 100.0, "BR": 100.0}},
                "2": {"status": "转录中", "pcts": {"DL": 100.0, "TR": 45.0, "BR": 0.0}},
            }
        }
        self.assertFalse(autosub_launcher.check_all_completed(state))

if __name__ == "__main__":
    unittest.main()
