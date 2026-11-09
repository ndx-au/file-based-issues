# Issue board

This folder is the project's issue tracker. It is ordinary files in the repository. A status is a folder. An issue is one Markdown file in that folder. The filename is the issue ID.

Progress means moving the file from one status folder to another. The ID stays the same. The full title lives in the file's front matter and can change without a rename.

## Status folders

Any directory here whose name does not start with `_` or `.` is a status. The board does not enforce an order. An issue can move from `done` back to `doing`.

These stages are the starting set:

| Folder | Meaning |
| --- | --- |
| `inbox` | Captured, not yet accepted |
| `backlog` | Accepted, not started |
| `doing` | In progress |
| `done` | Finished |

A new stage is a new directory plus a `.keep` file, so the empty folder stays in the repository. Creating an issue never creates a missing stage. That keeps a typo from becoming a status.

These names are reserved and are not issues: `README.md`, `AGENTS.md`, `do.py`, `options.json`, and `_template.md`. `_people/` and `_archive/` are reserved folders.

## Issue IDs

An ID is a lowercase word or hyphenated phrase that approximates the title, 1–48 characters: `export-notes`. The same pattern applies to status folder names.

The ID is unique across the whole board. `backlog/export-notes.md` and `doing/export-notes.md` cannot both exist. Pick a different ID when one is already taken. The filename does not change when the issue moves or the title is edited.

## Front matter

`do.py` writes this front matter into every new issue:

```yaml
---
id: export-notes
title: "Export the monthly notes"
status: backlog
created: 2026-11-09T12:42:00Z
updated: 2026-11-09T12:42:00Z
---
```

`id` matches the filename. `status` matches the parent folder. `created` and `updated` are UTC times like `2026-11-09T12:42:00Z`. Leave `id` and `created` alone. Set `updated` when you change the file. After a move, `do.py` rewrites `status` and `updated`.

Two optional fields have a shared meaning:

```yaml
owner: "@nickname"
blocked_by:
  - other-issue-id
```

`blocked_by` records a relationship. It does not stop a move. Other keys are welcome when a project wants them. `do.py` keeps those keys and does not interpret them. Prefer a single line per extra key, for example `priority: high`.

## Issue body

The template starts with two sections:

- **Outcome** — what is true when the issue is finished.
- **Notes** — a dated log. Append lines of the form `- 2026-11-09T12:42:00Z what changed`.

Add further sections when they help. Keep related files elsewhere in the repository and link them by path. The status folder stays one Markdown file per issue, plus `.keep` while the folder is empty.

## People

`@nickname` in an issue is an optional mention. A mention does not require a profile.

To record a person, add `.issues/_people/<nickname>.md`. The nickname uses the same form as an issue ID and matches the filename. The file's only required field is `nickname`. Ask that person what else belongs in the file, such as a name, role, or contact. Do not put secrets in it.

## Commands

Run these from anywhere. The board is the directory that contains `do.py`. `python3` means any Python 3.9+ interpreter.

```bash
python3 .issues/do.py --new backlog/export-notes --title "Export the monthly notes"
python3 .issues/do.py --move export-notes doing
python3 .issues/do.py --list
python3 .issues/do.py --list doing
python3 .issues/do.py --check
python3 .issues/do.py --archive export-notes,other-issue
python3 .issues/do.py --restore export-notes
```

`--new` copies `_template.md` and prints the new path, such as `backlog/export-notes.md`. It accepts an optional `.md` suffix and refuses a second slash, `..`, or uppercase. Exit status `0` means the file was created. If the ID exists anywhere on the board, the command exits `1` and names that file.

`--move` takes the ID and the destination stage. It finds the file, moves it, and updates `status`.

`--list` prints `stage/id` lines, sorted. A stage name limits the list.

`--check` checks unique IDs, names, front matter, that `status` matches the folder, and that every `blocked_by` entry is an issue on the board or in an archive. A clean board prints nothing and exits `0`.

Create, move, archive, and restore through `do.py`. Edit the title, body, `updated`, and optional keys in the file itself. If a file was dragged into another folder by hand, set `status` to that folder name and run `--check`.

## Archive

`--archive` takes a comma-separated list of up to 20 IDs. Spaces after commas are ignored. The issues are stored in `_archive/YYYY-MM.bz2` and then removed from the status folders. The name is the UTC month of the archive action. Each file is a bzip2-compressed tar; members keep the path they had on the board, such as `done/export-notes.md`. A later archive in the same month is added to that bundle. An ID that is already archived cannot be created again.

`--restore` copies those members back to the same stage paths and removes them from the bundle. An empty bundle is deleted. The destination stage must already exist.

`blocked_by` may name an archived ID. `--check` reports an ID that is both on the board and in a bundle.

## Rolling archive

`options.json` can archive old issues at the start of every `do.py` command, including `--list` and `--check`. Notices go to stderr, so a list on stdout stays a list of `stage/id` lines.

```json
{
  "rolling_archive": {
    "enabled": true,
    "stage": "done",
    "keep": 40,
    "max_per_run": 20
  }
}
```

When `enabled` is true, the command counts issues in `stage` and archives the oldest ones by `updated` until `keep` remain, at most `max_per_run` each run. The shipped file keeps the 40 newest `done` issues. Set `enabled` to false to leave every finished issue on the board. Other top-level keys are left for a project to define; keys inside `rolling_archive` are only `enabled`, `stage`, `keep`, and `max_per_run`.
