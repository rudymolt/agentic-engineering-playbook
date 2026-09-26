import contextlib
import importlib.util
import io
import tempfile
import types
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("check_glossary", SCRIPT_DIR / "check-glossary.py")
check_glossary = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(check_glossary)


MONOLITH = """# Design glossary

## Components

### Medal Icon

**One-line definition.** The medal glyph shown beside podium results.

**Kitchen-sink anchor.** [medal icon](./ui-kitchen-sink.html#medal-icon)

Rendered inside a `result-row`.

### Result Row

**One-line definition.** One athlete's result in a list.

**Kitchen-sink anchor.** [result row](./ui-kitchen-sink.html#result-row)
"""

KITCHEN_SINK = '<html><body><div id="medal-icon"></div><div id="result-row"></div></body></html>'


class CheckGlossaryTest(unittest.TestCase):
    def make_glossary(self, tmp: Path) -> tuple[Path, Path]:
        source = tmp / "DESIGN-GLOSSARY.md"
        source.write_text(MONOLITH)
        kitchen_sink = tmp / "ui-kitchen-sink.html"
        kitchen_sink.write_text(KITCHEN_SINK)
        outdir = tmp / "design-glossary"
        with contextlib.redirect_stdout(io.StringIO()):
            exit_code = check_glossary.cmd_split(
                types.SimpleNamespace(source=str(source), outdir=str(outdir))
            )
        self.assertEqual(exit_code, 0)
        return outdir, kitchen_sink

    def run_check(self, outdir: Path, kitchen_sink: Path | None = None) -> tuple[int, str]:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = check_glossary.cmd_check(
                types.SimpleNamespace(
                    glossary_dir=str(outdir),
                    kitchen_sink=str(kitchen_sink) if kitchen_sink else None,
                )
            )
        return exit_code, stdout.getvalue()

    def test_split_then_check_round_trip_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            outdir, kitchen_sink = self.make_glossary(Path(tmp))

            self.assertTrue((outdir / "components" / "medal-icon.md").exists())
            self.assertTrue((outdir / "components" / "result-row.md").exists())
            self.assertIn(
                "**Related.** [result-row](result-row.md)",
                (outdir / "components" / "medal-icon.md").read_text(),
            )

            exit_code, output = self.run_check(outdir, kitchen_sink)
            self.assertEqual(exit_code, 0, output)

    def test_broken_cross_link_fails_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            outdir, kitchen_sink = self.make_glossary(Path(tmp))
            entry = outdir / "components" / "medal-icon.md"
            entry.write_text(entry.read_text() + "\nSee also [ghost](ghost.md).\n")

            exit_code, output = self.run_check(outdir, kitchen_sink)
            self.assertEqual(exit_code, 1)
            self.assertIn("broken cross-link to 'ghost.md'", output)

    def test_stale_index_fails_until_rebuilt(self):
        with tempfile.TemporaryDirectory() as tmp:
            outdir, kitchen_sink = self.make_glossary(Path(tmp))
            entry = outdir / "components" / "result-row.md"
            entry.write_text(
                entry.read_text().replace(
                    "One athlete's result in a list.",
                    "One athlete's result and split times in a list.",
                )
            )

            exit_code, output = self.run_check(outdir, kitchen_sink)
            self.assertEqual(exit_code, 1)
            self.assertIn("stale", output)

            with contextlib.redirect_stdout(io.StringIO()):
                rebuilt = check_glossary.cmd_build_index(
                    types.SimpleNamespace(glossary_dir=str(outdir))
                )
            self.assertEqual(rebuilt, 0)
            exit_code, output = self.run_check(outdir, kitchen_sink)
            self.assertEqual(exit_code, 0, output)

    def test_missing_kitchen_sink_anchor_id_fails_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            outdir, kitchen_sink = self.make_glossary(Path(tmp))
            kitchen_sink.write_text(KITCHEN_SINK.replace('id="medal-icon"', 'id="renamed"'))

            exit_code, output = self.run_check(outdir, kitchen_sink)
            self.assertEqual(exit_code, 1)
            self.assertIn("anchor #medal-icon not found", output)

    def test_adr_index_round_trip_and_broken_link_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            adr_dir = Path(tmp) / "adr"
            adr_dir.mkdir()
            (adr_dir / "0001-use-sqlite.md").write_text(
                "# ADR 0001 — Use SQLite\n\nStatus: accepted\nDate: 2026-07-01\n"
            )
            (adr_dir / "0002-split-glossary.md").write_text(
                "# ADR 0002 — Split glossary\n\nStatus: accepted\nDate: 2026-07-02\n\n"
                "Supersedes part of [ADR 0001](0001-use-sqlite.md).\n"
            )

            with contextlib.redirect_stdout(io.StringIO()):
                built = check_glossary.cmd_adr_index(types.SimpleNamespace(adr_dir=str(adr_dir)))
            self.assertEqual(built, 0)

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                clean = check_glossary.cmd_check_adr(types.SimpleNamespace(adr_dir=str(adr_dir)))
            self.assertEqual(clean, 0, stdout.getvalue())

            (adr_dir / "0002-split-glossary.md").write_text(
                "# ADR 0002 — Split glossary\n\nStatus: accepted\nDate: 2026-07-02\n\n"
                "Supersedes part of [ADR 0003](0003-missing.md).\n"
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                broken = check_glossary.cmd_check_adr(types.SimpleNamespace(adr_dir=str(adr_dir)))
            self.assertEqual(broken, 1)
            self.assertIn("broken ADR link to '0003-missing.md'", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
