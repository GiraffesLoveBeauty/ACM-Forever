"""Protect provenance and offline avatar completeness in the existing release CI suite."""
import hashlib
import json
from pathlib import Path
import re
import struct
import unittest

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

if __name__ == '__main__':
    unittest.main()
