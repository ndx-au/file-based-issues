#!/usr/bin/env python3
"""Create, move, list, check, and archive the file-based issue board.

The board is the directory that contains this script. A status is a folder
whose name does not start with "_" or ".". An issue is one Markdown file in
a status folder, and the filename stem is the issue ID.
"""

import argparse
import io
import json
import os
import re
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path


SLUG = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
NICKNAME = re.compile(r"^@[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
KEY_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
ID_MAX = 48
ARCHIVE_BATCH_LIMIT = 20
ARCHIVE_NAME = re.compile(r"^\d{4}-\d{2}\.bz2$")
ROLLING_KEYS = {"enabled", "stage", "keep", "max_per_run"}
RESERVED_MD = {"README.md", "AGENTS.md", "_template.md"}
REQUIRED_KEYS = ("id", "title", "status", "created", "updated")


class BoardError(Exception):
    """A board command cannot be completed."""


def board_root():
    return Path(__file__).resolve().parent


def rel(root, path):
    return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()


def utc_stamp(now=None):
    if now is None:
        now = datetime.now(timezone.utc)
    if isinstance(now, datetime):
        if now.tzinfo is not None:
            now = now.astimezone(timezone.utc)
        return now.strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(now, str) and TIMESTAMP.fullmatch(now):
        return now
    raise BoardError(f"bad timestamp: {now}")


def yaml_quote(value):
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def unquote_scalar(value):
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return _unescape_double(value[1:-1])
    return value


def _unescape_double(inner):
    chars = []
    index = 0
    while index < len(inner):
        if inner[index] == "\\" and index + 1 < len(inner):
            chars.append(inner[index + 1])
            index += 2
            continue
        chars.append(inner[index])
        index += 1
    return "".join(chars)


def valid_slug(value):
    return bool(value) and len(value) <= ID_MAX and SLUG.fullmatch(value) is not None


def stage_dirs(root):
    root = Path(root)
    found = [
        path
        for path in root.iterdir()
        if path.is_dir() and not path.name.startswith((".", "_"))
    ]
    return sorted(found, key=lambda path: path.name)


def stage_names(root):
    return [path.name for path in stage_dirs(root) if SLUG.fullmatch(path.name)]


def require_stage(root, stage):
    if not SLUG.fullmatch(stage or ""):
        raise BoardError(f"bad stage name: {stage}")
    path = Path(root) / stage
    if not path.is_dir():
        known = ", ".join(stage_names(root)) or "(none)"
        raise BoardError(f"unknown stage: {stage} (stages: {known})")
    return path


def parse_stage_id(spec):
    text = str(spec).strip()
    if text.startswith(("/", "\\")) or "\\" in text:
        raise BoardError("expected STAGE/ID")
    if text.endswith(".md"):
        text = text[:-3]
    parts = text.split("/")
    if len(parts) != 2 or not parts[0] or not parts[1] or ".." in parts:
        raise BoardError("expected STAGE/ID")
    stage, issue_id = parts
    if not SLUG.fullmatch(stage):
        raise BoardError(f"bad stage name: {stage}")
    if not valid_slug(issue_id):
        raise BoardError(f"bad issue id: {issue_id}")
    return stage, issue_id


def clean_title(title):
    if not isinstance(title, str) or title.strip() == "":
        raise BoardError("title is empty")
    title = title.strip()
    if any(char in title for char in ("\n", "\r", "{{")):
        raise BoardError("title must be a single line")
    return title


def issue_files(root):
    files = []
    for stage in stage_dirs(root):
        children = sorted(stage.iterdir(), key=lambda path: path.name)
        files.extend(path for path in children if path.is_file() and path.suffix == ".md")
    return files


def valid_issue_ids(root):
    found = set()
    for path in issue_files(root):
        if valid_slug(path.stem) and SLUG.fullmatch(path.parent.name):
            found.add(path.stem)
    return found


def find_issue(root, issue_id):
    if not valid_slug(issue_id):
        raise BoardError(f"bad issue id: {issue_id}")
    matches = [
        path
        for path in issue_files(root)
        if path.stem == issue_id and SLUG.fullmatch(path.parent.name)
    ]
    if not matches:
        raise BoardError(f"issue not found: {issue_id}")
    if len(matches) > 1:
        listed = ", ".join(rel(root, path) for path in matches)
        raise BoardError(f"duplicate issue id {issue_id}: {listed}")
    return matches[0]


def split_document(text):
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    return text[4:end], text[end + 5 :]


def parse_fields(front_matter):
    fields = {}
    errors = []
    lines = front_matter.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if line[0] in " \t":
            errors.append("unexpected indented line in front matter")
            index += 1
            continue
        if ":" not in line:
            errors.append("bad front matter line")
            index += 1
            continue
        key, rest = line.split(":", 1)
        key = key.strip()
        if KEY_NAME.fullmatch(key) is None:
            errors.append(f"bad front matter key: {key}")
            index += 1
            continue
        if key in fields:
            errors.append(f"duplicate front matter key: {key}")
        rest = rest.strip()
        if rest == "":
            items = []
            index += 1
            while index < len(lines) and lines[index].startswith("  - "):
                items.append(unquote_scalar(lines[index][4:].strip()))
                index += 1
            if index < len(lines) and lines[index][:1] in " \t":
                errors.append(f"{key} has an unsupported value")
                while index < len(lines) and lines[index][:1] in " \t":
                    index += 1
            fields[key] = items
            continue
        if rest == "[]":
            fields[key] = []
        else:
            fields[key] = unquote_scalar(rest)
        index += 1
    return fields, errors


def replace_scalar(front_matter, key, value):
    pattern = re.compile(rf"^{re.escape(key)}:.*$", re.MULTILINE)
    if pattern.search(front_matter) is None:
        raise BoardError(f"missing front matter key: {key}")
    return pattern.sub(lambda _match: f"{key}: {value}", front_matter, count=1)


def render_template(template, issue_id, title, stage, stamp):
    needle = 'title: "{{title}}"'
    if needle not in template or "{{id}}" not in template or "{{created}}" not in template:
        raise BoardError("template is missing placeholders")
    text = template.replace(needle, f"title: {yaml_quote(title)}", 1)
    text = text.replace("{{title}}", title)
    text = text.replace("{{id}}", issue_id)
    text = text.replace("{{status}}", stage)
    text = text.replace("{{created}}", stamp)
    if "{{" in text:
        raise BoardError("template has unfilled placeholders")
    return text


def write_exclusive(path, text):
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    descriptor = os.open(path, flags, 0o644)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def write_exclusive_bytes(path, payload):
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    descriptor = os.open(path, flags, 0o644)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)


def create_issue(root, spec, title, now=None):
    root = Path(root)
    stage, issue_id = parse_stage_id(spec)
    title = clean_title(title)
    require_stage(root, stage)
    try:
        existing = find_issue(root, issue_id)
    except BoardError as exc:
        if str(exc).startswith("issue not found:"):
            existing = None
        else:
            raise
    if existing is not None:
        raise BoardError(f"issue already exists: {rel(root, existing)}")
    index, archive_errors = scan_archives(root)
    if archive_errors:
        raise BoardError(archive_errors[0])
    if issue_id in index:
        raise BoardError(f"issue already exists: {index[issue_id]}")
    template_path = root / "_template.md"
    if not template_path.is_file():
        raise BoardError("missing template: _template.md")
    stamp = utc_stamp(now)
    rendered = render_template(
        template_path.read_text(encoding="utf-8"), issue_id, title, stage, stamp
    )
    destination = root / stage / f"{issue_id}.md"
    try:
        write_exclusive(destination, rendered)
    except FileExistsError:
        raise BoardError(f"issue already exists: {rel(root, destination)}") from None
    return rel(root, destination)


def move_issue(root, issue_id, stage, now=None):
    root = Path(root)
    destination_dir = require_stage(root, stage)
    source = find_issue(root, issue_id)
    destination = destination_dir / source.name
    if source == destination:
        return rel(root, source)
    text = _read_text(source, root)
    parts = split_document(text)
    if parts is None:
        raise BoardError(f"missing front matter: {rel(root, source)}")
    front_matter, body = parts
    try:
        front_matter = replace_scalar(front_matter, "status", stage)
        front_matter = replace_scalar(front_matter, "updated", utc_stamp(now))
    except BoardError as exc:
        raise BoardError(f"{exc} in {rel(root, source)}") from exc
    rendered = f"---\n{front_matter}\n---\n{body}"
    try:
        write_exclusive(destination, rendered)
    except FileExistsError:
        raise BoardError(f"issue already exists: {rel(root, destination)}") from None
    source.unlink()
    return rel(root, destination)


def list_issues(root, stage=None):
    root = Path(root)
    if stage:
        require_stage(root, stage)
    lines = []
    for path in issue_files(root):
        if not valid_slug(path.stem) or SLUG.fullmatch(path.parent.name) is None:
            continue
        if stage and path.parent.name != stage:
            continue
        lines.append(f"{path.parent.name}/{path.stem}")
    return sorted(lines)


def check_board(root):
    root = Path(root)
    errors = []
    _settings, option_errors = parse_rolling_options(root)
    errors.extend(option_errors)
    index, archive_errors = scan_archives(root)
    errors.extend(archive_errors)
    for stage in stage_dirs(root):
        if SLUG.fullmatch(stage.name) is None:
            errors.append(f"bad stage name: {stage.name}")
    grouped = {}
    ids = valid_issue_ids(root) | set(index)
    for path in issue_files(root):
        relative = rel(root, path)
        if not valid_slug(path.stem):
            errors.append(f"bad issue id: {relative}")
            continue
        if path.stem in index:
            errors.append(f"issue is also archived: {relative} in {index[path.stem]}")
        grouped.setdefault(path.stem, []).append(relative)
        errors.extend(_check_issue(root, path, ids))
    for issue_id, paths in sorted(grouped.items()):
        if len(paths) > 1:
            errors.append(f"duplicate issue id {issue_id}: {', '.join(paths)}")
    errors.extend(_misplaced_markdown(root))
    people = root / "_people"
    if people.is_dir():
        for path in sorted(people.iterdir(), key=lambda item: item.name):
            if path.is_file() and path.suffix == ".md":
                errors.extend(_check_person(root, path))
    return sorted(errors)


def _read_text(path, root):
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeError:
        raise BoardError(f"issue is not utf-8 text: {rel(root, path)}") from None


def _check_issue(root, path, ids):
    relative = rel(root, path)
    try:
        text = _read_text(path, root)
    except BoardError as exc:
        return [str(exc)]
    parts = split_document(text)
    if parts is None:
        return [f"missing front matter: {relative}"]
    fields, parse_errors = parse_fields(parts[0])
    messages = [f"{message} in {relative}" for message in parse_errors]
    for key in REQUIRED_KEYS:
        if not isinstance(fields.get(key), str):
            messages.append(f"missing front matter key: {key} in {relative}")
    issue_id = fields.get("id")
    if isinstance(issue_id, str) and issue_id != path.stem:
        messages.append(f"id does not match filename: {relative} has {issue_id}")
    status = fields.get("status")
    if isinstance(status, str) and status != path.parent.name:
        messages.append(f"status does not match folder: {relative} has {status}")
    title = fields.get("title")
    if isinstance(title, str) and title.strip() == "":
        messages.append(f"title is empty: {relative}")
    for key in ("created", "updated"):
        value = fields.get(key)
        if isinstance(value, str) and TIMESTAMP.fullmatch(value) is None:
            messages.append(f"bad timestamp for {key}: {relative}")
    if "owner" in fields and (
        not isinstance(fields["owner"], str) or NICKNAME.fullmatch(fields["owner"]) is None
    ):
        messages.append(f"owner must be @nickname: {relative}")
    if "blocked_by" in fields:
        blocked = fields["blocked_by"]
        if not isinstance(blocked, list):
            messages.append(f"blocked_by must be a list: {relative}")
        else:
            for item in blocked:
                if not isinstance(item, str) or not valid_slug(item):
                    messages.append(f"blocked_by is not an issue id: {item} in {relative}")
                elif item not in ids:
                    messages.append(f"blocked_by is not on the board: {item} in {relative}")
    return messages


def _check_person(root, path):
    relative = rel(root, path)
    if not valid_slug(path.stem):
        return [f"bad person name: {relative}"]
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeError:
        return [f"person file is not utf-8 text: {relative}"]
    parts = split_document(text)
    if parts is None:
        return [f"missing front matter: {relative}"]
    fields, parse_errors = parse_fields(parts[0])
    messages = [f"{message} in {relative}" for message in parse_errors]
    nickname = fields.get("nickname")
    if not isinstance(nickname, str):
        messages.append(f"missing front matter key: nickname in {relative}")
    elif nickname != path.stem:
        messages.append(f"nickname does not match filename: {relative} has {nickname}")
    return messages


def _misplaced_markdown(root):
    misplaced = []
    for path in root.rglob("*.md"):
        parts = path.relative_to(root).parts
        if len(parts) == 1 and parts[0] in RESERVED_MD:
            continue
        if len(parts) == 2 and not parts[0].startswith((".", "_")):
            continue
        if len(parts) == 2 and parts[0] == "_people":
            continue
        misplaced.append(f"markdown file is in the wrong place: {rel(root, path)}")
    return misplaced


def parse_id_list(value):
    if isinstance(value, (list, tuple)):
        parts = [str(part).strip() for part in value]
    else:
        if not isinstance(value, str) or value.strip() == "":
            raise BoardError("missing issue ids")
        parts = [part.strip() for part in value.split(",")]
    if not parts or any(part == "" for part in parts):
        raise BoardError("missing issue id in list")
    if len(parts) > ARCHIVE_BATCH_LIMIT:
        raise BoardError(f"limit is {ARCHIVE_BATCH_LIMIT} issues")
    seen = set()
    for issue_id in parts:
        if not valid_slug(issue_id):
            raise BoardError(f"bad issue id: {issue_id}")
        if issue_id in seen:
            raise BoardError(f"duplicate issue id in list: {issue_id}")
        seen.add(issue_id)
    return parts


def _member_identity(name):
    parts = name.split("/")
    if len(parts) != 2 or parts[0] in {".", ".."} or parts[1] in {".", ".."}:
        return None, None
    stage, filename = parts
    if not filename.endswith(".md"):
        return None, None
    issue_id = filename[:-3]
    if SLUG.fullmatch(stage) is None or not valid_slug(issue_id):
        return None, None
    return issue_id, stage


def read_archive(path, label):
    members = {}
    try:
        bundle = tarfile.open(path, "r:bz2")
    except (tarfile.TarError, OSError, EOFError) as exc:
        raise BoardError(f"unreadable archive: {label}") from exc
    with bundle:
        for member in bundle.getmembers():
            issue_id, stage = _member_identity(member.name)
            if issue_id is None or not member.isfile():
                raise BoardError(f"bad archive member: {label} has {member.name}")
            extracted = bundle.extractfile(member)
            if extracted is None:
                raise BoardError(f"bad archive member: {label} has {member.name}")
            if issue_id in members:
                raise BoardError(f"duplicate archived issue {issue_id}: {label}")
            members[issue_id] = (stage, extracted.read())
    return members


def _tar_bytes(members):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:bz2") as bundle:
        for issue_id in sorted(members):
            stage, payload = members[issue_id]
            info = tarfile.TarInfo(f"{stage}/{issue_id}.md")
            info.size = len(payload)
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            bundle.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def write_archive(path, members):
    if not members:
        if path.is_file():
            path.unlink()
        return
    path.parent.mkdir(exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(_tar_bytes(members))
    temporary.replace(path)


def scan_archives(root):
    root = Path(root)
    folder = root / "_archive"
    index = {}
    errors = []
    if not folder.exists():
        return index, errors
    if not folder.is_dir():
        return index, ["bad archive name: _archive"]
    for path in sorted(folder.iterdir(), key=lambda item: item.name):
        relative = rel(root, path)
        if not path.is_file() or ARCHIVE_NAME.fullmatch(path.name) is None:
            errors.append(f"bad archive name: {relative}")
            continue
        try:
            members = read_archive(path, relative)
        except BoardError as exc:
            errors.append(str(exc))
            continue
        for issue_id in members:
            if issue_id in index:
                errors.append(f"duplicate archived issue {issue_id}: {index[issue_id]}, {relative}")
                continue
            index[issue_id] = relative
    return index, errors


def _json_int(value, low, high):
    return not isinstance(value, bool) and isinstance(value, int) and low <= value <= high


def parse_rolling_options(root):
    path = Path(root) / "options.json"
    if not path.exists():
        return None, []
    if not path.is_file():
        return None, ["bad options.json: expected a file"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except UnicodeError:
        return None, ["bad options.json: expected utf-8 text"]
    except json.JSONDecodeError as exc:
        return None, [f"bad options.json: {exc.msg}"]
    if not isinstance(data, dict):
        return None, ["bad options.json: expected an object"]
    if "rolling_archive" not in data:
        return None, []
    block = data["rolling_archive"]
    if not isinstance(block, dict):
        return None, ["bad options.json: rolling_archive must be an object"]
    errors = []
    unknown = sorted(set(block) - ROLLING_KEYS)
    if unknown:
        errors.append("bad options.json: unknown rolling_archive keys: " + ", ".join(unknown))
    enabled = block.get("enabled", False)
    if not isinstance(enabled, bool):
        errors.append("bad options.json: rolling_archive.enabled must be true or false")
        enabled = False
    stage = block.get("stage", "done")
    if not isinstance(stage, str) or SLUG.fullmatch(stage) is None:
        errors.append("bad options.json: rolling_archive.stage must be a stage name")
        stage = None
    keep = block.get("keep", 40)
    if not _json_int(keep, 0, 500):
        errors.append("bad options.json: rolling_archive.keep must be an integer from 0 to 500")
        keep = None
    max_per_run = block.get("max_per_run", ARCHIVE_BATCH_LIMIT)
    if not _json_int(max_per_run, 1, ARCHIVE_BATCH_LIMIT):
        errors.append(
            "bad options.json: rolling_archive.max_per_run must be an integer "
            f"from 1 to {ARCHIVE_BATCH_LIMIT}"
        )
        max_per_run = None
    if errors or not enabled:
        return None, errors
    return {"stage": stage, "keep": keep, "max_per_run": max_per_run}, []


def archive_issues(root, ids, now=None):
    root = Path(root)
    parsed = parse_id_list(ids)
    index, errors = scan_archives(root)
    if errors:
        raise BoardError(errors[0])
    sources = []
    for issue_id in parsed:
        if issue_id in index:
            raise BoardError(f"issue already archived: {index[issue_id]}")
        sources.append(find_issue(root, issue_id))
    regime = utc_stamp(now)[:7]
    bundle = root / "_archive" / f"{regime}.bz2"
    label = f"_archive/{regime}.bz2"
    members = read_archive(bundle, label) if bundle.is_file() else {}
    lines = []
    for source in sources:
        if source.stem in members:
            raise BoardError(f"issue already archived: {label}")
        members[source.stem] = (source.parent.name, source.read_bytes())
        lines.append(f"{source.parent.name}/{source.stem}.md -> {label}")
    write_archive(bundle, members)
    for source in sources:
        try:
            source.unlink()
        except OSError as exc:
            raise BoardError(f"archived but not removed: {rel(root, source)}: {exc.strerror}") from exc
    return lines


def restore_issues(root, ids):
    root = Path(root)
    parsed = parse_id_list(ids)
    index, errors = scan_archives(root)
    if errors:
        raise BoardError(errors[0])
    by_bundle = {}
    for issue_id in parsed:
        if issue_id not in index:
            raise BoardError(f"archived issue not found: {issue_id}")
        try:
            live = find_issue(root, issue_id)
        except BoardError as exc:
            if str(exc).startswith("issue not found:"):
                live = None
            else:
                raise
        if live is not None:
            raise BoardError(f"issue already exists: {rel(root, live)}")
        by_bundle.setdefault(index[issue_id], []).append(issue_id)
    loaded = {}
    planned = []
    for bundle_rel, issue_ids in by_bundle.items():
        members = read_archive(root / bundle_rel, bundle_rel)
        loaded[bundle_rel] = members
        for issue_id in issue_ids:
            stage, payload = members[issue_id]
            require_stage(root, stage)
            planned.append((bundle_rel, issue_id, stage, payload))
    lines = []
    for bundle_rel, issue_id, stage, payload in planned:
        destination = root / stage / f"{issue_id}.md"
        try:
            write_exclusive_bytes(destination, payload)
        except FileExistsError:
            raise BoardError(f"issue already exists: {stage}/{issue_id}.md") from None
        lines.append(f"{bundle_rel} -> {stage}/{issue_id}.md")
    for bundle_rel, issue_ids in by_bundle.items():
        members = loaded[bundle_rel]
        for issue_id in issue_ids:
            del members[issue_id]
        write_archive(root / bundle_rel, members)
    return lines


def apply_rolling_archive(root, now=None):
    root = Path(root)
    settings, errors = parse_rolling_options(root)
    if errors:
        raise BoardError(errors[0])
    if settings is None:
        return []
    require_stage(root, settings["stage"])
    index, archive_errors = scan_archives(root)
    if archive_errors:
        raise BoardError(archive_errors[0])
    candidates = []
    for path in issue_files(root):
        if path.parent.name != settings["stage"] or not valid_slug(path.stem):
            continue
        if path.stem in index:
            continue
        try:
            text = _read_text(path, root)
        except BoardError:
            continue
        parts = split_document(text)
        if parts is None:
            continue
        fields, parse_errors = parse_fields(parts[0])
        updated = fields.get("updated")
        if (
            parse_errors
            or not isinstance(updated, str)
            or TIMESTAMP.fullmatch(updated) is None
            or fields.get("id") != path.stem
            or fields.get("status") != settings["stage"]
        ):
            continue
        candidates.append((updated, path.stem))
    candidates.sort()
    overflow = len(candidates) - settings["keep"]
    if overflow <= 0:
        return []
    chosen = [issue_id for _updated, issue_id in candidates[: min(overflow, settings["max_per_run"])]]
    return archive_issues(root, chosen, now=now)


def main(argv=None, root=None, now=None):
    parser = argparse.ArgumentParser(description="Create, move, list, check, and archive file-based issues.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--new", metavar="STAGE/ID", help="create STAGE/ID from _template.md")
    group.add_argument("--move", nargs=2, metavar=("ID", "STAGE"), help="move ID into STAGE")
    group.add_argument("--list", nargs="?", const="", metavar="STAGE", help="list stage/id lines")
    group.add_argument("--check", action="store_true", help="report board inconsistencies")
    group.add_argument("--archive", metavar="ID[,ID...]", help="archive up to 20 issues into _archive/YYYY-MM.bz2")
    group.add_argument("--restore", metavar="ID[,ID...]", help="restore archived issues to the stage they left")
    parser.add_argument("--title", help="full issue title, required with --new")
    args = parser.parse_args(argv)
    root = Path(root) if root is not None else board_root()
    try:
        if args.title is not None and not args.new:
            raise BoardError("--title is only valid with --new")
        for line in apply_rolling_archive(root, now=now):
            print(line, file=sys.stderr)
        if args.new:
            if not args.title:
                raise BoardError("missing --title")
            print(create_issue(root, args.new, args.title, now=now))
        elif args.move:
            print(move_issue(root, args.move[0], args.move[1], now=now))
        elif args.list is not None:
            for line in list_issues(root, args.list or None):
                print(line)
        elif args.check:
            problems = check_board(root)
            if problems:
                print("\n".join(problems), file=sys.stderr)
                return 1
        elif args.archive:
            for line in archive_issues(root, args.archive, now=now):
                print(line)
        elif args.restore:
            for line in restore_issues(root, args.restore):
                print(line)
    except BoardError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
