"""Fail-closed GitHub Release response parser and action planner."""

import argparse
import json
import re
import sys
import subprocess
import time
from pathlib import Path
from urllib.parse import quote

if __package__:
    from .check_release_assets import local_assets, verify_assets
else:
    from check_release_assets import local_assets, verify_assets
from collections import namedtuple


Response = namedtuple("Response", "status headers body")
HEX_SHA = re.compile(r"^[0-9a-f]{40}$")
STATUS_LINE = re.compile(r"^HTTP/\d(?:\.\d)?\s+(\d{3})(?:\s|$)")
MISSING_ACTIONS = ["create-draft", "upload", "verify", "publish"]
DRAFT_ACTIONS = ["delete-draft"] + MISSING_ACTIONS


class ReleaseStateError(ValueError):
    pass


def parse_included_response(raw):
    """Parse gh api --include stdout; stderr is deliberately not an input."""
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    if not isinstance(raw, bytes) or not raw:
        raise ReleaseStateError("gh api response stdout is empty")
    match = STATUS_LINE.match(raw.splitlines()[0].decode("ascii", "replace"))
    if match is None:
        raise ReleaseStateError("missing or malformed HTTP status line")
    separator = b"\r\n\r\n"
    if separator in raw:
        head, body = raw.split(separator, 1)
    elif b"\n\n" in raw:
        head, body = raw.split(b"\n\n", 1)
    else:
        raise ReleaseStateError("truncated headers or missing header/body separator")
    lines = head.splitlines()[1:]
    if not lines:
        raise ReleaseStateError("HTTP response has no headers")
    headers = {}
    for line in lines:
        if b":" not in line:
            raise ReleaseStateError("malformed or truncated HTTP header")
        name, value = line.split(b":", 1)
        if not re.fullmatch(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name):
            raise ReleaseStateError("invalid HTTP header name")
        key = name.decode("ascii").lower()
        if key in headers:
            raise ReleaseStateError("duplicate HTTP header: " + key)
        headers[key] = value.decode("latin-1").strip()
    if not body.strip():
        raise ReleaseStateError("HTTP response body is empty")
    return Response(int(match.group(1)), headers, body.strip())


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ReleaseStateError("duplicate JSON field: " + key)
        value[key] = item
    return value


def _json_value(response):
    try:
        value = json.loads(response.body.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, ValueError) as exc:
        raise ReleaseStateError("response body is not valid JSON: %s" % exc)
    return value


def _json_body(response):
    value = _json_value(response)
    if not isinstance(value, dict):
        raise ReleaseStateError("response JSON must be an object")
    return value


def _http_error(response):
    message = ""
    try:
        body = _json_body(response)
        message = str(body.get("message", "")).lower()
    except ReleaseStateError:
        pass
    if response.status in (403, 429):
        if response.headers.get("x-ratelimit-remaining") == "0":
            reset = response.headers.get("x-ratelimit-reset", "unknown")
            return "primary rate limit exceeded (reset=%s)" % reset
        if "retry-after" in response.headers or "secondary rate limit" in message:
            return "secondary rate limit exceeded"
        return "request forbidden or rate limited (HTTP %d)" % response.status
    return "GitHub API returned HTTP %d" % response.status


def decide(response, tag, expected_sha, actual_tag_commit):
    if not HEX_SHA.fullmatch(expected_sha or "") or not HEX_SHA.fullmatch(actual_tag_commit or ""):
        raise ReleaseStateError("expected and resolved tag commits must be full 40-character SHAs")
    if expected_sha != actual_tag_commit:
        raise ReleaseStateError("tag commit does not match the workflow commit")
    if response.status == 404:
        error = _json_body(response)
        if error.get("message") != "Not Found" or error.get("status", "404") != "404":
            raise ReleaseStateError("contradictory HTTP 404 response")
        return {"state": "missing", "reason": "release endpoint returned HTTP 404",
                "actions": list(MISSING_ACTIONS)}
    if response.status != 200:
        raise ReleaseStateError(_http_error(response))
    release = _json_body(response)
    if release.get("tag_name") != tag:
        raise ReleaseStateError("release tag_name does not match requested tag")
    if type(release.get("draft")) is not bool:
        raise ReleaseStateError("release draft field must be a boolean")
    if not isinstance(release.get("assets"), list):
        raise ReleaseStateError("release assets field must be a list")
    if "id" not in release or type(release["id"]) is not int or release["id"] <= 0:
        raise ReleaseStateError("release id is missing or invalid")
    if release["draft"] and (release.get("immutable") is True or release.get("published_at") is not None):
        raise ReleaseStateError("contradictory draft metadata")
    if release["draft"]:
        return {"state": "draft", "reason": "an unpublished draft exists",
                "release_id": release["id"], "actions": list(DRAFT_ACTIONS)}
    return {"state": "published", "reason": "release is already published",
            "release_id": release["id"], "actions": []}


def _run(args):
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _request(runner, endpoint):
    result = runner(["gh", "api", endpoint, "--include"])
    response = parse_included_response(result.stdout)
    if (response.status < 400) != (result.returncode == 0):
        raise ReleaseStateError("gh exit code contradicts HTTP status")
    return response


def _command(runner, args):
    result = runner(args)
    if result.returncode != 0:
        # Never interpret stderr as a release-state signal or print untrusted diagnostics.
        raise ReleaseStateError("gh %s failed (exit %s)" % (" ".join(args[1:3]), result.returncode))
    return result.stdout


def publish(repo, tag, expected_sha, directory, notes, runner=_run):
    """Execute only the closed action sequence returned by decide; stop on any failure."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ReleaseStateError("invalid repository name")
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag):
        raise ReleaseStateError("release tag must be vMAJOR.MINOR.PATCH")
    endpoint = "repos/%s/releases/tags/%s" % (repo, quote(tag, safe=""))

    def current():
        # Explicit refs/tags avoids a branch of the same name shadowing the tag.
        commit = _request(runner, "repos/%s/commits/%s" % (repo, quote("refs/tags/" + tag, safe="")))
        if commit.status != 200:
            raise ReleaseStateError(_http_error(commit))
        actual = _json_body(commit).get("sha")
        response = _request(runner, endpoint)
        initial = decide(response, tag, expected_sha, actual)
        if initial["state"] != "missing":
            return initial
        # The tag endpoint returns published releases only. Authenticated listing
        # includes drafts; exhaust pagination before deciding that none exists.
        matches = []
        page = 1
        while True:
            listing = _request(runner, "repos/%s/releases?per_page=100&page=%d" % (repo, page))
            if listing.status != 200:
                raise ReleaseStateError(_http_error(listing))
            items = _json_value(listing)
            if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
                raise ReleaseStateError("invalid releases listing")
            for item in items:
                if not isinstance(item.get("tag_name"), str):
                    raise ReleaseStateError("release listing entry has no tag_name")
                if item["tag_name"] == tag:
                    # Validate each candidate before using its ID in another request.
                    candidate = decide(Response(200, {}, json.dumps(item).encode()),
                                       tag, expected_sha, actual)
                    matches.append(candidate)
            if len(items) < 100:
                break
            page += 1
        if len(matches) > 1:
            raise ReleaseStateError("multiple releases match the requested tag")
        if not matches:
            return initial
        release_response = _request(runner, "repos/%s/releases/%d" % (repo, matches[0]["release_id"]))
        if release_response.status != 200:
            raise ReleaseStateError(_http_error(release_response))
        observed = decide(release_response, tag, expected_sha, actual)
        if observed["release_id"] != matches[0]["release_id"]:
            raise ReleaseStateError("release identity differs from listing")
        return observed

    plan = current()
    if not plan["actions"]:
        return plan
    # Check local inputs before deleting an existing draft.
    directory, notes = Path(directory), Path(notes)
    local_assets(directory)
    if not notes.read_text(encoding="utf-8").strip():
        raise ReleaseStateError("release notes are empty")
    release_id = plan.get("release_id")
    verified = False

    def require_draft():
        observed = current()
        if observed["state"] != "draft" or observed["release_id"] != release_id:
            raise ReleaseStateError("draft identity changed during publication")

    def delete_draft():
        require_draft()
        _command(runner, ["gh", "release", "delete", tag, "--repo", repo, "--yes"])

    def create_draft():
        nonlocal release_id
        if current()["state"] != "missing":
            raise ReleaseStateError("release appeared before draft creation")
        _command(runner, ["gh", "release", "create", tag, "--repo", repo,
                          "--verify-tag", "--draft", "--title", tag, "--notes-file", str(notes)])
        # Newly created drafts can briefly be absent from the listing. Retry
        # reads only, never creation; errors and unexpected publication still stop.
        for attempt in range(5):
            observed = current()
            if observed["state"] != "missing":
                break
            if attempt < 4:
                time.sleep(2)
        if observed["state"] != "draft":
            raise ReleaseStateError("created release is not a visible draft")
        release_id = observed["release_id"]

    def upload():
        require_draft()
        paths = [str(directory / name) for name in sorted(local_assets(directory))]
        _command(runner, ["gh", "release", "upload", tag] + paths + ["--repo", repo])

    def verify():
        nonlocal verified
        require_draft()
        raw = _command(runner, ["gh", "api", "repos/%s/releases/%d/assets?per_page=100" % (repo, release_id),
                                "--paginate", "--slurp"])
        pages = json.loads(raw)
        if not isinstance(pages, list) or any(not isinstance(page, list) for page in pages):
            raise ReleaseStateError("invalid paginated assets response")
        verify_assets(directory, [asset for page in pages for asset in page])
        verified = True

    def finalize():
        if not verified:
            raise ReleaseStateError("cannot publish without asset verification")
        require_draft()
        _command(runner, ["gh", "release", "edit", tag, "--repo", repo, "--draft=false"])
        observed = current()
        if observed["state"] != "published" or observed["release_id"] != release_id:
            raise ReleaseStateError("published release could not be confirmed")

    handlers = {"delete-draft": delete_draft, "create-draft": create_draft,
                "upload": upload, "verify": verify, "publish": finalize}
    if any(action not in handlers for action in plan["actions"]):
        raise ReleaseStateError("unknown release action")
    for action in plan["actions"]:
        handlers[action]()
    return plan


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--repo")
    parser.add_argument("--assets-dir")
    parser.add_argument("--notes-file")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--tag-commit")
    parser.add_argument("--gh-exit-code", type=int)
    args = parser.parse_args(argv)
    try:
        if args.publish:
            if not all([args.repo, args.assets_dir, args.notes_file]):
                raise ReleaseStateError("publication requires repo, assets-dir and notes-file")
            plan = publish(args.repo, args.tag, args.expected_sha, args.assets_dir, args.notes_file)
        else:
            if args.gh_exit_code is None or args.tag_commit is None:
                raise ReleaseStateError("planning requires gh-exit-code and tag-commit")
            response = parse_included_response(sys.stdin.buffer.read())
            if (response.status < 400) != (args.gh_exit_code == 0):
                raise ReleaseStateError("gh exit code contradicts the HTTP status line")
            plan = decide(response, args.tag, args.expected_sha, args.tag_commit)
    except (ValueError, OSError) as exc:
        sys.stderr.write("release-state: %s\n" % exc)
        return 2
    sys.stdout.write(json.dumps(plan, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
