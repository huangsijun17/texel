"""Exercise the actual gh executor with a deterministic in-memory transport."""
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from tools.release_state import ReleaseStateError, publish

SHA = 'a' * 40


class FakeGh:
    def __init__(self, state='missing', fail=None, history=0):
        self.release = None if state == 'missing' else {
            'id': 12, 'tag_name': 'v0.2.0', 'draft': state == 'draft', 'assets': []}
        self.calls = []
        self.mutations = []
        self.fail = fail
        self.assets = []
        self.history = history
        self.invisible_reads = 0

    def __call__(self, args):
        self.calls.append(args)
        if args[1] == 'api':
            endpoint = args[2]
            if '/commits/' in endpoint:
                body, status = {'sha': SHA}, 200
                if self.fail == 'moved':
                    body['sha'] = 'b' * 40
            elif endpoint.endswith('/assets?per_page=100'):
                return subprocess.CompletedProcess(args, 0, json.dumps([self.assets]).encode(), b'')
            elif '/releases?per_page=100&page=' in endpoint:
                page = int(endpoint.rsplit('=', 1)[1])
                entries = [{'tag_name': 'v0.0.%d' % n} for n in range(self.history)]
                visible = self.release is not None and self.invisible_reads == 0
                entries += [self.release] if visible else []
                if self.invisible_reads:
                    self.invisible_reads -= 1
                if self.fail == 'duplicate-draft':
                    entries += [self.release]
                body, status = entries[(page - 1) * 100:page * 100], 200
                if self.fail == 'list-forbidden' or (self.fail == 'second-page-failed' and page == 2):
                    body, status = {'message': 'Forbidden'}, 403
            elif endpoint.endswith('/releases/13') or endpoint.endswith('/releases/12'):
                body, status = self.release, 200
            else:
                body, status = (self.release, 200) if self.release and not self.release['draft'] else ({'message': 'Not Found', 'status': '404'}, 404)
                if self.fail == 'network':
                    return subprocess.CompletedProcess(args, 1, b'', b'connection failed')
                if self.fail == 'forbidden':
                    status, body = 403, {'message': 'Forbidden'}
            raw = ('HTTP/2.0 %d Test\nContent-Type: application/json\n\n' % status).encode() + json.dumps(body).encode()
            return subprocess.CompletedProcess(args, int(status >= 400), raw, b'')
        action = args[2]
        self.mutations.append(action)
        if self.fail == action:
            return subprocess.CompletedProcess(args, 1, b'', b'injected failure')
        if action == 'delete':
            self.release = None
        elif action == 'create':
            self.release = {'id': 13, 'tag_name': 'v0.2.0', 'draft': True, 'assets': []}
            if self.fail == 'delayed-create':
                self.invisible_reads = 2
            elif self.fail == 'invisible-create':
                self.invisible_reads = 20
        elif action == 'upload':
            for value in args[4:]:
                if value == '--repo':
                    break
                path = Path(value)
                payload = path.read_bytes()
                self.assets.append(dict(name=path.name, size=len(payload), state='uploaded',
                                        digest='sha256:' + hashlib.sha256(payload).hexdigest()))
            if self.fail == 'verify':
                self.assets[0]['digest'] = None
        elif action == 'edit':
            self.release['draft'] = False
        return subprocess.CompletedProcess(args, 0, b'', b'')


class ReleaseExecutorTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assets = self.root / 'assets'
        self.assets.mkdir()
        (self.assets / 'payload.bin').write_bytes(b'payload')
        (self.assets / 'SHA256SUMS').write_text(hashlib.sha256(b'payload').hexdigest() + '  payload.bin\n')
        self.notes = self.root / 'notes.md'
        self.notes.write_text('release notes')

    def run_release(self, gh):
        return publish('owner/repo', 'v0.2.0', SHA, self.assets, self.notes, runner=gh)

    def test_missing_uploads_before_publish(self):
        gh = FakeGh()
        self.run_release(gh)
        self.assertEqual(['create', 'upload', 'edit'], gh.mutations)
        self.assertFalse(gh.release['draft'])

    def test_created_draft_visibility_delay_only_retries_reads(self):
        from unittest.mock import patch
        gh = FakeGh(fail='delayed-create')
        with patch('tools.release_state.time.sleep') as sleep:
            self.run_release(gh)
        self.assertEqual(['create', 'upload', 'edit'], gh.mutations)
        self.assertEqual(2, sleep.call_count)

    def test_created_draft_visibility_timeout_never_uploads_or_publishes(self):
        from unittest.mock import patch
        gh = FakeGh(fail='invisible-create')
        with patch('tools.release_state.time.sleep') as sleep:
            with self.assertRaisesRegex(ReleaseStateError, 'created release'):
                self.run_release(gh)
        self.assertEqual(['create'], gh.mutations)
        self.assertEqual(4, sleep.call_count)

    def test_old_partial_draft_rebuilt_and_tag_preserved(self):
        gh = FakeGh('draft')
        gh.release['body'] = 'old build'
        gh.assets = []
        self.run_release(gh)
        self.assertEqual(['delete', 'create', 'upload', 'edit'], gh.mutations)
        self.assertNotIn('--cleanup-tag', str(gh.calls))

    def test_draft_after_first_page_is_rebuilt(self):
        gh = FakeGh('draft', history=100)
        self.run_release(gh)
        self.assertEqual(['delete', 'create', 'upload', 'edit'], gh.mutations)
        self.assertTrue(any('page=2' in call[2] for call in gh.calls if call[1] == 'api'))

    def test_listing_failure_or_duplicate_draft_never_mutates(self):
        for failure in ['second-page-failed', 'duplicate-draft']:
            gh = FakeGh('draft', failure, history=100)
            with self.subTest(failure=failure), self.assertRaises(ReleaseStateError):
                self.run_release(gh)
            self.assertEqual([], gh.mutations)

    def test_published_noop_even_without_local_files(self):
        gh = FakeGh('published')
        publish('owner/repo', 'v0.2.0', SHA, self.root / 'absent', self.root / 'absent', runner=gh)
        self.assertEqual([], gh.mutations)

    def test_upload_or_validation_failure_never_publishes(self):
        for failure in ['upload', 'verify', 'create', 'delete']:
            with self.subTest(failure=failure):
                gh = FakeGh('draft', failure)
                with self.assertRaises((ReleaseStateError, ValueError)):
                    self.run_release(gh)
                self.assertNotIn('edit', gh.mutations)

    def test_query_failure_and_moved_tag_have_no_mutations(self):
        for failure in ['network', 'forbidden', 'moved', 'list-forbidden']:
            gh = FakeGh(fail=failure)
            with self.assertRaises(ReleaseStateError):
                self.run_release(gh)
            self.assertEqual([], gh.mutations)

    def test_failed_verification_can_be_retried_from_draft(self):
        gh = FakeGh(fail='verify')
        with self.assertRaises(ValueError):
            self.run_release(gh)
        self.assertTrue(gh.release['draft'])
        gh.fail, gh.assets = None, []
        self.run_release(gh)
        self.assertEqual(['create', 'upload', 'delete', 'create', 'upload', 'edit'], gh.mutations)

    def test_invalid_local_manifest_has_no_mutations(self):
        (self.assets / 'SHA256SUMS').write_text('invalid')
        gh = FakeGh('draft')
        with self.assertRaises(ValueError):
            self.run_release(gh)
        self.assertEqual([], gh.mutations)


if __name__ == '__main__':
    unittest.main()
