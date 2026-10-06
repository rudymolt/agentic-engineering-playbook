"""CI parallelism must retain every ordinary unittest module and failure."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import tempfile
import unittest

from parallel_verification import run_parallel, test_files


ROOT = Path(__file__).resolve().parents[2]


class ParallelVerificationTests(unittest.TestCase):
    def test_file_shards_match_the_whole_public_suite(self):
        directory = ROOT / "v0.5/scripts"
        files = test_files(directory)
        self.assertTrue(files)
        self.assertEqual(len(files), len(set(files)))
        loader = unittest.TestLoader()
        whole = loader.discover(str(directory), pattern="test_*.py").countTestCases()
        sharded = sum(unittest.TestLoader().discover(str(directory), pattern=name).countTestCases()
                      for name in files)
        self.assertEqual(sharded, whole)

    def test_parallel_commands_run_every_shard_and_report_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            commands = []
            for index, exit_code in enumerate((0, 3, 0)):
                marker = root / str(index)
                commands.append((sys.executable, "-c",
                                 "from pathlib import Path; import sys; "
                                 "Path(sys.argv[1]).write_text('ran'); sys.exit(int(sys.argv[2]))",
                                 str(marker), str(exit_code)))
            output = StringIO()
            with redirect_stdout(output):
                result = run_parallel(commands, cwd=root, jobs=2)
            self.assertEqual(result, 3)
            self.assertEqual([path.read_text() for path in sorted(root.iterdir())], ["ran"] * 3)
            self.assertIn("exit 3", output.getvalue())


if __name__ == "__main__":
    unittest.main()
