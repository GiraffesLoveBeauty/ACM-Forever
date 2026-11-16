import gzip
import unittest

from quart import Quart, jsonify
from feat.api.acm_api.read_transport import optimize_response


class ReadTransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = Quart(__name__)
        self.app.after_request(optimize_response)

        @self.app.get('/api/mobile/v1/capabilities')
        async def capabilities():
            return jsonify({'api_version': 1, 'features': {'example': True}})

        @self.app.get('/api/wiki/pages')
        async def wiki():
            result = jsonify({'body': 'public repeated text ' * 500})
            result.headers['Cache-Control'] = 'public, max-age=0, must-revalidate'
            result.headers['ETag'] = '"public-wiki"'
            return result

        @self.app.get('/api/me/profile')
        async def private():
            result = jsonify({'secret': 'private ' * 500})
            result.headers['Cache-Control'] = 'no-store'
            return result

        self.client = self.app.test_client()

    async def test_public_conditional_request_and_private_exclusion(self):
        first = await self.client.get('/api/mobile/v1/capabilities')
        etag = first.headers['ETag']
        unchanged = await self.client.get('/api/mobile/v1/capabilities', headers={'If-None-Match': etag})
        self.assertEqual(unchanged.status_code, 304)
        self.assertEqual(await unchanged.get_data(), b'')
        private = await self.client.get('/api/me/profile', headers={'Accept-Encoding': 'gzip', 'If-None-Match': '*'})
        self.assertEqual(private.status_code, 200)
        self.assertEqual(private.headers['Cache-Control'], 'no-store')
        self.assertNotIn('ETag', private.headers)
        self.assertNotIn('Content-Encoding', private.headers)

    async def test_gzip_is_negotiated_for_public_json_and_weak_validators(self):
        plain = await self.client.get('/api/wiki/pages')
        packed = await self.client.get('/api/wiki/pages', headers={'Accept-Encoding': 'gzip'})
        self.assertEqual(packed.headers['Content-Encoding'], 'gzip')
        self.assertIn('Accept-Encoding', packed.vary)
        self.assertEqual(gzip.decompress(await packed.get_data()), await plain.get_data())
        self.assertLess(len(await packed.get_data()), len(await plain.get_data()) / 10)
        refused = await self.client.get('/api/wiki/pages', headers={'Accept-Encoding': 'gzip;q=0'})
        self.assertNotIn('Content-Encoding', refused.headers)
