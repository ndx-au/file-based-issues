# Issue board — agent instructions

Read [README.md](README.md) for the human description of this board. Follow the rules below when you create, move, or edit issues.

The parent folder is the status. The filename is the ID. `do.py` is the only creator, mover, and archiver. Commands use `python3`, or any Python 3.9+ interpreter. No packages are required.

## Create

```bash
python3 .issues/do.py --new STAGE/issue-id --title "Full title"
```

- Choose a lowercase hyphenated ID, 1–48 characters, that approximates the title (`^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$`).
- The ID must be unused in every status folder and in `_archive/`. On collision the script exits `1` and prints `issue already exists: <path>`. Choose a different ID. Leave the filename free of numeric suffixes.
- The stage folder must already exist. A missing stage is a typo or a deliberate new folder, which needs a directory and a `.keep` file. `--new` does not create stages.
- Exit `0` and the printed path mean the file was created from `_template.md`. Then fill **Outcome** and any project-specific front matter.

## Move

```bash
python3 .issues/do.py --move issue-id STAGE
```

The script finds the file, moves it, and rewrites `status` and `updated`. The filename stays the same. Any existing stage is a legal destination, including a move from `done` back to `doing`. `blocked_by` does not block a move. A `blocked_by` ID may be on the board or in `_archive/`.

## Edit

Edit the Markdown in place.

- You may change `title`, `updated`, `owner`, `blocked_by`, project-specific keys, and the body.
- Leave `id` and `created` unchanged. Leave the filename unchanged.
- Set `updated` to the current UTC time `YYYY-MM-DDTHH:MM:SSZ` whenever you change the file.
- Append notes as `- 2026-11-09T12:42:00Z what changed`.
- Extra front matter keys are allowed. Keep each one on a single line unless it is `blocked_by`, which is a list of issue IDs:

```yaml
owner: "@nickname"
blocked_by:
  - other-issue-id
priority: high
```

`owner` and `blocked_by` are the optional fields with a shared meaning. `priority` above is only an example of a project-specific key.

- Link supporting files by repository path. Do not add notes, attachments, or copies beside the issue file.
- After a front matter edit, run `python3 .issues/do.py --check`.

The folder wins if it and `status` disagree. Set `status` to the folder name, then run `--check`.

## People

`@nickname` in prose is optional. A mention does not need a file under `_people/`.

Create `.issues/_people/<nickname>.md` only after asking what that person wants recorded. The nickname matches the filename and is the only required field:

```yaml
---
nickname: nickname
---
```

Store no secrets, tokens, or credentials in a person file or an issue.

## Archive

Every `do.py` command applies [options.json](options.json) first. The shipped settings archive the oldest `done` issues when more than 40 remain, up to 20 per run. Rolling notices are printed on stderr. Leave `inbox`, `backlog`, and `doing` on the board unless the user asks for those IDs.

```bash
python3 .issues/do.py --archive issue-id,other-id
python3 .issues/do.py --restore issue-id
```

`--archive` accepts at most 20 IDs. It appends the files to `_archive/YYYY-MM.bz2` (UTC month of the run) and then deletes them. The whole list is refused when any ID is missing, repeated, or already archived. Use `--restore` to put an issue back on its previous stage path. Leave the `.bz2` bundles unchanged by hand.

## Commands

```bash
python3 .issues/do.py --list
python3 .issues/do.py --list doing
python3 .issues/do.py --check
```

`--list` prints `stage/id` lines. `--check` must pass before you treat an issue change as finished. It reports duplicate IDs, bad names, Markdown files outside an issue or person slot, missing required keys, a `status` that differs from the parent folder, a `blocked_by` ID that is neither on the board nor in an archive, and an ID that is in both places. It does not fail on an unknown `@nickname`. Rolling archive runs before `--check` when `options.json` enables it.
