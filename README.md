# file-based-issues

A project issue tracker made of Markdown files. In `.issues/doing/export-notes.md`, the folder says the work is in progress, the filename gives it the ID `export-notes`, and the file holds its title, outcome, and notes. The ID stays the same when the issue moves.

The board lives alongside the project, so you can read it in an editor and review issue changes with the code they describe. It works offline with Python 3.9+ and the standard library.

## Adopt it

1. Copy the [`.issues/` directory](.issues/) into the target project root. Include the script, options, template, both guides, and the `.keep` files in `inbox/`, `backlog/`, `doing/`, and `done/`.
2. Add this line to the target project's agent instructions so agents use the board consistently.

   > Follow `.issues/AGENTS.md`. Create, move, list, check, archive, and restore issues with `python3 .issues/do.py`.

3. From the target project root, run `python3 .issues/do.py --check`. A fresh board exits successfully with no output.

## Track a piece of work

Run these commands from the project root.

```bash
python3 .issues/do.py --new inbox/export-notes --title "Export the monthly notes"
python3 .issues/do.py --move export-notes doing
python3 .issues/do.py --list doing
```

The last command prints `doing/export-notes`. Edit the **Outcome** and **Notes** in `.issues/doing/export-notes.md`, and set `updated` to the current UTC time when you edit. When the work is finished, run `python3 .issues/do.py --move export-notes done`. The script updates the status and timestamp on each move.

Use your roadmap to order work and refer to each issue by ID. If you want a sequence in the IDs themselves, start with a letter, as in `p01-export-notes`. Projects can add front matter fields such as `priority` and document their conventions in an agent skill. See the [board guide](.issues/README.md) and [agent instructions](.issues/AGENTS.md).

## Finished issues

By default, each command checks whether more than 40 eligible issues remain in `done/`. It archives up to 20 of the oldest by `updated` in a monthly bundle. Restore an issue to its previous folder with `python3 .issues/do.py --restore export-notes`. To keep finished issues in place, set `rolling_archive.enabled` to `false` in the [board options](.issues/options.json).

## Tests

Run `python3 -m unittest discover -s tests -v` from this repository's root. To use the same suite in an adopting project, copy [the test file](tests/test_issue_board.py) into a top-level `tests/` directory beside `.issues/`.

## License

[Apache License 2.0](LICENSE).
