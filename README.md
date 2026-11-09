# file-based-issues

A project issue tracker made of folders and Markdown files. Python 3 is the only requirement. The standard library is enough: `do.py` installs nothing and opens no network connection.

The tracker in this repository is the [`.issues/`](.issues/) directory. Copy that directory into the root of the project that needs it.

## Why this exists

Hosted issue trackers assume a Git host, an account, and a service that both people and agents can log into. Plenty of projects do not have that. A tree may live in another version-control system, stay private, or simply be a directory of files. The work list still has to sit next to the work, where an editor can open it and a review can show the diff.

This board keeps that list in the project itself. A status is a folder. An issue is one Markdown file, and the filename is its ID. Progress is moving the file. The full title, dates, and notes stay in the file, so the folder name is enough to see where the work stands.

A short Python script is part of the copy so agents do not invent a second copy of an ID or leave `status` pointing at the wrong folder. People can still read and edit the Markdown. Finished issues can be packed into a monthly `.bz2` archive so a long-lived board does not fill the tree. There is no database, no account, and no daemon.

## Adopt it

An agent implementing this in another project should do only the following:

1. Copy `.issues/` from this repository into the target project root. Keep `do.py`, `options.json`, `_template.md`, `README.md`, `AGENTS.md`, and the stage folders `inbox/`, `backlog/`, `doing/`, and `done/`, including each `.keep` file.
2. Point the target project's agent instructions at `.issues/AGENTS.md`. State that creating, moving, archiving, and restoring issues go through `python3 .issues/do.py`.
3. From the target project root, run `python3 .issues/do.py --check`. A new board prints nothing and exits 0.
4. Leave [`.issues/options.json`](.issues/options.json) as copied unless the project wants a different rolling archive. Set `rolling_archive.enabled` to `false` to keep every finished issue in `done/`.

Use `python3`, or another Python 3.9+ interpreter. The examples do not depend on a virtual environment. Copy `tests/test_issue_board.py` only when the target has a top-level `tests/` directory beside `.issues/`; the test file finds the script at `../.issues/do.py`. Run it with `python3 -m unittest discover -s tests -v`.

Create an issue when there is real work:

```bash
python3 .issues/do.py --new inbox/export-notes --title "Export the monthly notes"
python3 .issues/do.py --move export-notes doing
python3 .issues/do.py --list
```

Human rules for day-to-day use are in [`.issues/README.md`](.issues/README.md). Agent rules are in [`.issues/AGENTS.md`](.issues/AGENTS.md).

## License

[Apache License 2.0](LICENSE).
