"""File-based issue board: create, move, list, check, and archive."""

import contextlib
import importlib.util
import io
import json
import shutil
import tarfile
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("issues_do", REPO / ".issues" / "do.py")
do = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(do)


class IssueBoardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        shutil.copy(REPO / ".issues" / "_template.md", self.root / "_template.md")
        for stage in ("inbox", "backlog", "doing", "done"):
            directory = self.root / stage
            directory.mkdir()
            (directory / ".keep").write_text("\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_new_fills_template(self):
        created = do.create_issue(
            self.root,
            "backlog/story-schema",
            'Say "hello"',
            now="2026-11-09T12:42:00Z",
        )
        self.assertEqual(created, "backlog/story-schema.md")
        text = (self.root / created).read_text(encoding="utf-8")
        self.assertIn("id: story-schema\n", text)
        self.assertIn('title: "Say \\"hello\\""\n', text)
        self.assertIn("status: backlog\n", text)
        self.assertIn("created: 2026-11-09T12:42:00Z\n", text)
        self.assertIn("updated: 2026-11-09T12:42:00Z\n", text)
        self.assertIn('# Say "hello"\n', text)
        self.assertIn("## Outcome\n", text)
        self.assertIn("- 2026-11-09T12:42:00Z created\n", text)
        self.assertEqual(do.check_board(self.root), [])

    def test_collision_across_stages(self):
        do.create_issue(self.root, "doing/story-schema", "Tighten the story schema")
        with self.assertRaises(do.BoardError) as caught:
            do.create_issue(self.root, "backlog/story-schema.md", "Again")
        self.assertEqual(str(caught.exception), "issue already exists: doing/story-schema.md")
        self.assertFalse((self.root / "backlog" / "story-schema.md").exists())

    def test_bad_slug_and_unknown_stage(self):
        with self.assertRaises(do.BoardError) as bad_id:
            do.create_issue(self.root, "backlog/Story_Schema", "Title")
        self.assertIn("bad issue id", str(bad_id.exception))
        with self.assertRaises(do.BoardError) as too_long:
            do.create_issue(self.root, "backlog/" + ("a" * 49), "Title")
        self.assertIn("bad issue id", str(too_long.exception))
        with self.assertRaises(do.BoardError) as escaped:
            do.create_issue(self.root, "backlog/../escape", "Title")
        self.assertIn("expected STAGE/ID", str(escaped.exception))
        with self.assertRaises(do.BoardError) as missing:
            do.create_issue(self.root, "no-such/ok-id", "Title")
        self.assertIn("unknown stage: no-such (stages: backlog, doing, done, inbox)", str(missing.exception))
        self.assertFalse((self.root / "no-such").exists())

    def test_move_updates_status_and_keeps_extra_keys(self):
        do.create_issue(
            self.root, "backlog/story-schema", "Tighten the story schema", now="2026-11-09T00:00:00Z"
        )
        path = self.root / "backlog" / "story-schema.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "updated:", 'owner: "@ada"\npriority: high\nupdated:', 1
            ),
            encoding="utf-8",
        )
        moved = do.move_issue(self.root, "story-schema", "doing", now="2026-11-09T01:00:00Z")
        self.assertEqual(moved, "doing/story-schema.md")
        self.assertFalse(path.exists())
        text = (self.root / moved).read_text(encoding="utf-8")
        self.assertIn("id: story-schema\n", text)
        self.assertIn("status: doing\n", text)
        self.assertIn("created: 2026-11-09T00:00:00Z\n", text)
        self.assertIn("updated: 2026-11-09T01:00:00Z\n", text)
        self.assertIn('owner: "@ada"\n', text)
        self.assertIn("priority: high\n", text)
        self.assertEqual(do.check_board(self.root), [])
        returned = do.move_issue(self.root, "story-schema", "done", now="2026-11-09T02:00:00Z")
        self.assertEqual(returned, "done/story-schema.md")
        back = do.move_issue(self.root, "story-schema", "doing", now="2026-11-09T03:00:00Z")
        self.assertEqual(back, "doing/story-schema.md")

    def test_list_order(self):
        do.create_issue(self.root, "inbox/zeta-item", "Zeta")
        do.create_issue(self.root, "doing/alpha-item", "Alpha")
        do.create_issue(self.root, "backlog/middle-item", "Middle")
        self.assertEqual(
            do.list_issues(self.root),
            ["backlog/middle-item", "doing/alpha-item", "inbox/zeta-item"],
        )
        self.assertEqual(do.list_issues(self.root, "doing"), ["doing/alpha-item"])

    def test_check_failures(self):
        do.create_issue(self.root, "backlog/story-schema", "Tighten the story schema")
        issue = self.root / "backlog" / "story-schema.md"
        issue.write_text(
            issue.read_text(encoding="utf-8").replace("status: backlog", "status: doing", 1),
            encoding="utf-8",
        )
        self.assertIn(
            "status does not match folder: backlog/story-schema.md has doing",
            do.check_board(self.root),
        )
        issue.write_text(
            issue.read_text(encoding="utf-8").replace("status: doing", "status: backlog", 1),
            encoding="utf-8",
        )
        issue.write_text(
            issue.read_text(encoding="utf-8").replace(
                "updated:", "blocked_by:\n  - missing-issue\nupdated:", 1
            ),
            encoding="utf-8",
        )
        self.assertIn(
            "blocked_by is not on the board: missing-issue in backlog/story-schema.md",
            do.check_board(self.root),
        )
        doing = self.root / "doing" / "story-schema.md"
        doing.write_text(
            issue.read_text(encoding="utf-8")
            .replace("status: backlog", "status: doing", 1)
            .replace("blocked_by:\n  - missing-issue\n", ""),
            encoding="utf-8",
        )
        self.assertIn(
            "duplicate issue id story-schema: backlog/story-schema.md, doing/story-schema.md",
            do.check_board(self.root),
        )
        title_line = next(line for line in issue.read_text(encoding="utf-8").splitlines(True) if line.startswith("title:"))
        issue.write_text(issue.read_text(encoding="utf-8").replace(title_line, ""), encoding="utf-8")
        self.assertIn(
            "missing front matter key: title in backlog/story-schema.md",
            do.check_board(self.root),
        )
        (self.root / "notes.md").write_text("# Loose note\n", encoding="utf-8")
        self.assertIn(
            "markdown file is in the wrong place: notes.md",
            do.check_board(self.root),
        )

    def test_mentions_and_people(self):
        do.create_issue(self.root, "inbox/ask-ada", "Ask Ada")
        issue = self.root / "inbox" / "ask-ada.md"
        issue.write_text(
            issue.read_text(encoding="utf-8") + "\nSee @ada for the recording.\n",
            encoding="utf-8",
        )
        self.assertEqual(do.check_board(self.root), [])
        people = self.root / "_people"
        people.mkdir()
        (people / "ada.md").write_text("---\nnickname: someone-else\n---\n\n", encoding="utf-8")
        self.assertIn(
            "nickname does not match filename: _people/ada.md has someone-else",
            do.check_board(self.root),
        )

    def test_cli_exit_codes(self):
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = do.main(
                ["--new", "backlog/cli-issue", "--title", "CLI issue"],
                root=self.root,
            )
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue().strip(), "backlog/cli-issue.md")
        self.assertEqual(err.getvalue(), "")
        out.seek(0)
        out.truncate()
        err.seek(0)
        err.truncate()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = do.main(
                ["--new", "doing/cli-issue", "--title", "Again"],
                root=self.root,
            )
        self.assertEqual(code, 1)
        self.assertIn("issue already exists: backlog/cli-issue.md", err.getvalue())
        err.seek(0)
        err.truncate()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = do.main(["--check"], root=self.root)
        self.assertEqual(code, 0)
        self.assertEqual(err.getvalue(), "")

    def write_options(self, enabled=True, keep=1, max_per_run=20, stage="done"):
        payload = {
            "rolling_archive": {
                "enabled": enabled,
                "stage": stage,
                "keep": keep,
                "max_per_run": max_per_run,
            }
        }
        (self.root / "options.json").write_text(json.dumps(payload) + "\n", encoding="utf-8")

    def test_archive_restore_and_reuse(self):
        do.create_issue(self.root, "done/alpha-item", "Alpha", now="2026-11-01T00:00:00Z")
        do.create_issue(self.root, "doing/beta-item", "Beta", now="2026-11-02T00:00:00Z")
        original = (self.root / "done" / "alpha-item.md").read_bytes()
        lines = do.archive_issues(
            self.root, "beta-item, alpha-item", now="2026-11-09T00:00:00Z"
        )
        self.assertEqual(
            lines,
            [
                "doing/beta-item.md -> _archive/2026-11.bz2",
                "done/alpha-item.md -> _archive/2026-11.bz2",
            ],
        )
        self.assertFalse((self.root / "done" / "alpha-item.md").exists())
        self.assertFalse((self.root / "doing" / "beta-item.md").exists())
        with tarfile.open(self.root / "_archive" / "2026-11.bz2", "r:bz2") as bundle:
            self.assertEqual(
                sorted(bundle.getnames()),
                ["doing/beta-item.md", "done/alpha-item.md"],
            )
        do.create_issue(self.root, "backlog/gamma-item", "Gamma", now="2026-12-01T00:00:00Z")
        december = do.archive_issues(self.root, "gamma-item", now="2026-12-02T00:00:00Z")
        self.assertEqual(december, ["backlog/gamma-item.md -> _archive/2026-12.bz2"])
        with self.assertRaises(do.BoardError) as reused:
            do.create_issue(self.root, "inbox/alpha-item", "Alpha again")
        self.assertEqual(str(reused.exception), "issue already exists: _archive/2026-11.bz2")
        with self.assertRaises(do.BoardError) as again:
            do.archive_issues(self.root, "alpha-item", now="2026-11-09T00:00:00Z")
        self.assertEqual(str(again.exception), "issue already archived: _archive/2026-11.bz2")
        restored = do.restore_issues(self.root, "alpha-item")
        self.assertEqual(restored, ["_archive/2026-11.bz2 -> done/alpha-item.md"])
        self.assertEqual((self.root / "done" / "alpha-item.md").read_bytes(), original)
        with tarfile.open(self.root / "_archive" / "2026-11.bz2", "r:bz2") as bundle:
            self.assertEqual(bundle.getnames(), ["doing/beta-item.md"])
        do.restore_issues(self.root, "beta-item")
        self.assertFalse((self.root / "_archive" / "2026-11.bz2").exists())
        do.create_issue(self.root, "backlog/needs-alpha", "Needs alpha", now="2026-11-03T00:00:00Z")
        do.archive_issues(self.root, "alpha-item", now="2026-11-09T00:00:00Z")
        blocked = self.root / "backlog" / "needs-alpha.md"
        blocked.write_text(
            blocked.read_text(encoding="utf-8").replace(
                "updated:", "blocked_by:\n  - alpha-item\nupdated:", 1
            ),
            encoding="utf-8",
        )
        self.assertEqual(do.check_board(self.root), [])

    def test_archive_refuses_the_whole_list(self):
        do.create_issue(self.root, "done/keep-me", "Keep me")
        with self.assertRaises(do.BoardError) as missing:
            do.archive_issues(self.root, "keep-me,missing-id")
        self.assertEqual(str(missing.exception), "issue not found: missing-id")
        self.assertTrue((self.root / "done" / "keep-me.md").exists())
        self.assertFalse((self.root / "_archive").exists())
        with self.assertRaises(do.BoardError) as repeated:
            do.archive_issues(self.root, "keep-me,keep-me")
        self.assertIn("duplicate issue id in list", str(repeated.exception))
        too_many = ",".join(f"item-{number:02d}" for number in range(21))
        with self.assertRaises(do.BoardError) as limited:
            do.archive_issues(self.root, too_many)
        self.assertEqual(str(limited.exception), "limit is 20 issues")
        self.assertTrue((self.root / "done" / "keep-me.md").exists())

    def test_rolling_archive_keeps_newest_done_issues(self):
        self.write_options(keep=1, max_per_run=2)
        for name, stamp in (
            ("older-item", "2026-11-01T00:00:00Z"),
            ("middle-item", "2026-11-02T00:00:00Z"),
            ("newer-item", "2026-11-03T00:00:00Z"),
        ):
            do.create_issue(self.root, f"done/{name}", name, now=stamp)
        do.create_issue(self.root, "doing/active-item", "Active", now="2026-10-01T00:00:00Z")
        lines = do.apply_rolling_archive(self.root, now="2026-11-09T00:00:00Z")
        self.assertEqual(
            lines,
            [
                "done/older-item.md -> _archive/2026-11.bz2",
                "done/middle-item.md -> _archive/2026-11.bz2",
            ],
        )
        self.assertEqual(
            do.list_issues(self.root),
            ["doing/active-item", "done/newer-item"],
        )
        self.assertEqual(do.apply_rolling_archive(self.root, now="2026-11-09T00:00:00Z"), [])
        self.write_options(enabled=False, keep=0)
        self.assertEqual(do.apply_rolling_archive(self.root), [])
        self.assertTrue((self.root / "done" / "newer-item.md").exists())

    def test_rolling_archive_runs_before_the_command(self):
        self.write_options(keep=0, max_per_run=20)
        do.create_issue(self.root, "done/old-item", "Old", now="2026-11-01T00:00:00Z")
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = do.main(["--list"], root=self.root, now="2026-11-09T00:00:00Z")
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(err.getvalue(), "done/old-item.md -> _archive/2026-11.bz2\n")
        (self.root / "options.json").write_text("{", encoding="utf-8")
        self.assertTrue(
            any(line.startswith("bad options.json:") for line in do.check_board(self.root))
        )

    def test_shipped_rolling_options(self):
        settings, errors = do.parse_rolling_options(REPO / ".issues")
        self.assertEqual(errors, [])
        self.assertEqual(settings["stage"], "done")
        self.assertEqual(settings["keep"], 40)
        self.assertEqual(settings["max_per_run"], 20)


if __name__ == "__main__":
    unittest.main()
