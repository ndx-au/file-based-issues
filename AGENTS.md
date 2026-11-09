# Adopting file-based-issues

This is a public repository. Treat every file here as publishable: no secrets, tokens, credentials, private hostnames, tailnet or LAN URLs, or internal lab topology.

This repository is the specification and the files to copy. The `.issues/` directory here is the reference board for this project alone, not the board of some other project. Do not file another project's work here.

When asked to implement this system in a target project, follow [README.md](README.md):

- Copy `.issues/` into the target project root, including `do.py`, `options.json`, `_template.md`, `README.md`, `AGENTS.md`, and the `inbox/`, `backlog/`, `doing/`, and `done/` folders with their `.keep` files.
- Point the target project's agent instructions at `.issues/AGENTS.md`.
- Create, move, list, check, archive, and restore only with `python3 .issues/do.py`. Do not create, move, or rename issue files by hand.
- Run `python3 .issues/do.py --check` in the target project. A new board exits 0 with no output.
- Do not add packages, a database, a network client, or a hosted tracker. Python 3.9+ from the standard library is the requirement.
- Leave the design minimal. Prefer editing docs and `do.py` over new tooling.

## Working in this repository

- Read [`.issues/AGENTS.md`](.issues/AGENTS.md) before creating or moving an issue here.
- Keep issue text generic and free of secrets; this board is public with the rest of the tree.
- After board changes, run `python3 .issues/do.py --check`.
- After changing `do.py` or the tests, run `python3 -m unittest discover -s tests -v`.
