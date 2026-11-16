"""Publication gates use synthetic attribution; no real Review is fabricated."""
import copy
import hashlib
import struct
import io
import json
from pathlib import Path
import sys
import unittest
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from release_credits import validate_release_credits, bundled_credits, requires_review_record, ASSET


def reviewed_fixture(version='1.0.0'):
    return dict(schemaVersion=1, repository='GiraffesLoveBeauty/ACM-Forever',
        historyOwnerNote='Synthetic test record only.', people=[dict(login='test-reviewer', role='Test fixture')],
        versions={version: dict(status='reviewed', pr=1, scope='Synthetic completed Review',
            uploaders=['test-reviewer'], reviewRequesters=['test-reviewer'], reviewers=['test-reviewer'],
            publishers=[], evidence=['https://github.com/GiraffesLoveBeauty/ACM-Forever/pull/1'])})


def apk_fixture(credits=None):
    out = io.BytesIO()
    with ZipFile(out, 'w') as archive:
        archive.writestr(ASSET, json.dumps(credits or reviewed_fixture()))
    return out.getvalue()


class ReleaseCreditsTests(unittest.TestCase):
    def test_current_pending_record_blocks_tag_and_packaged_snapshot(self):
        value = reviewed_fixture()
        value['versions']['1.0.0']['status'] = 'development'
        with self.assertRaises(ValueError): validate_release_credits(value, '1.0.0')
        with self.assertRaises(ValueError): bundled_credits(io.BytesIO(apk_fixture(value)), '1.0.0')

    def test_completed_record_and_exact_packaged_source(self):
        value = reviewed_fixture()
        self.assertEqual(value, bundled_credits(io.BytesIO(apk_fixture(value)), '1.0.0', value))
        different = copy.deepcopy(value)
        different['versions']['1.0.0']['scope'] += ' changed'
        with self.assertRaises(ValueError): bundled_credits(io.BytesIO(apk_fixture(value)), '1.0.0', different)

    def test_no_first_person_missing_actor_or_invented_publication(self):
        for key, bad in [('scope', '本人 Review'), ('scope', '候选，尚未 Review'),
                         ('reviewers', []), ('reviewRequesters', ['unknown']), ('pr', 0),
                         ('evidence', ['https://example.invalid/1']), ('publishers', ['test-reviewer'])]:
            value = reviewed_fixture()
            value['versions']['1.0.0'][key] = bad
            with self.subTest(key=key, bad=bad), self.assertRaises(ValueError): validate_release_credits(value, '1.0.0')

    def test_historical_immutable_releases_keep_their_original_contract(self):
        self.assertFalse(requires_review_record('0.2.30'))
        self.assertTrue(requires_review_record('1.0.0'))
        self.assertTrue(requires_review_record('1.1.0'))

    def test_actual_source_current_record_is_still_pending_review(self):
        path = Path(__file__).resolve().parents[1] / 'app/app/src/main/assets/releases/credits.json'
        value = json.loads(path.read_text(encoding='utf-8'))
        current = value['versions']['1.0.0']
        # This assertion tracks the current development stage, not a permanent release rule.
        if current['status'] == 'development':
            self.assertEqual([], current['reviewers'])
            with self.assertRaises(ValueError): validate_release_credits(value, '1.0.0')
        else:
            validate_release_credits(value, '1.0.0')

ASSETS = Path(__file__).resolve().parents[1] / 'app/app/src/main/assets'

class ReleaseCreditsTest(unittest.TestCase):
    def test_each_person_has_a_bounded_png_matching_recorded_digest(self):
        credits = json.loads((ASSETS/'releases/credits.json').read_text(encoding='utf-8'))
        logins = set()
        for person in credits['people']:
            with self.subTest(login=person['login']):
                self.assertNotIn(person['login'],logins)
                logins.add(person['login'])
                self.assertRegex(person['avatar'],r'^credits/avatars/[0-9]+\.png$')
                body = (ASSETS/person['avatar']).read_bytes()
                self.assertLessEqual(len(body),65536)
                self.assertEqual(b'\x89PNG\r\n\x1a\n',body[:8])
                width,height = struct.unpack('>II',body[16:24])
                self.assertTrue(16<=width<=96 and 16<=height<=96)
                self.assertEqual(person['avatarSha256'],hashlib.sha256(body).hexdigest())
                self.assertRegex(person['avatarSource'],r'^https://avatars\.githubusercontent\.com/(?:u|in)/[0-9]+\?v=4$')
        self.assertEqual(set(credits['thanks']),logins)

    def test_version_rows_have_evidence_and_no_invented_independent_early_reviews(self):
        credits = json.loads((ASSETS/'releases/credits.json').read_text(encoding='utf-8'))
        history = json.loads((ASSETS/'releases/history.json').read_text(encoding='utf-8'))
        self.assertEqual({row['versionName'] for row in history['entries']},set(credits['versions']))
        for version,record in credits['versions'].items():
            with self.subTest(version=version):
                self.assertTrue(record['uploaders'])
                if tuple(map(int,version.split('.'))) <= (0,2,21):
                    self.assertEqual(['MiaoJJ13445'],record['uploaders'])
                if record['reviewRequesters'] or record['reviewers']:
                    self.assertGreater(record['pr'],0)
                    self.assertTrue(record['evidence'])
                if record['pr']==48 and version!='0.2.13':
                    self.assertIn('未找到本版本独立评审记录',record['scope'])
        self.assertEqual('unpublished',credits['versions']['0.2.14']['status'])
        self.assertEqual('unpublished',credits['versions']['0.2.16']['status'])
