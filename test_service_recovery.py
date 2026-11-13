import unittest
from unittest.mock import AsyncMock, patch
import httpx
from gemini_client import generate_json, ModelError


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_malformed_json_retried_before_returning(self):
        responses=[httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':text}]}}]})
                   for text in ('{"reason":"missing comma" "correct":true}', '{"correct":false}')]
        with patch.dict('os.environ',{'GOOGLE_API_KEY':'test'}), \
             patch('gemini_client.httpx.AsyncClient.post',AsyncMock(side_effect=responses)) as post, \
             patch('gemini_client.reserve',AsyncMock()):
            self.assertEqual(await generate_json('test'),{'correct':False})
            self.assertEqual(post.await_count,2)

    async def test_transient_503_then_success(self):
        responses=[httpx.Response(503), httpx.Response(200,json={
            'candidates':[{'content':{'parts':[{'text':'{"answer":5}'}]}}]})]
        with patch.dict('os.environ',{'GOOGLE_API_KEY':'test'}), \
             patch('gemini_client.httpx.AsyncClient.post',AsyncMock(side_effect=responses)) as post, \
             patch('gemini_client.reserve',AsyncMock()), \
             patch('gemini_client.asyncio.sleep',AsyncMock()):
            self.assertEqual(await generate_json('test'),{'answer':5})
            self.assertEqual(post.await_count,2)

    async def test_unavailability_is_bounded(self):
        with patch.dict('os.environ',{'GOOGLE_API_KEY':'test'}), \
             patch('gemini_client.httpx.AsyncClient.post',AsyncMock(return_value=httpx.Response(503))) as post, \
             patch('gemini_client.reserve',AsyncMock()), \
             patch('gemini_client.asyncio.sleep',AsyncMock()):
            with self.assertRaisesRegex(ModelError,'after 3 attempts'):
                await generate_json('test')
            self.assertEqual(post.await_count,3)
