import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from unified_controller import UnifiedController


class RequestNavigationTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_link_replaces_old_deltamath_page(self):
        old = 'https://www.deltamath.com/app/student/1/2/old'
        target = 'https://www.deltamath.com/app/student/1/2/new'
        page = MagicMock(url=old)
        page.goto = AsyncMock()
        page.locator.return_value.count = AsyncMock(return_value=1)
        browser = SimpleNamespace(lock=asyncio.Lock(), page=AsyncMock(return_value=page))
        with tempfile.TemporaryDirectory() as directory:
            controller = UnifiedController(browser, None, None, None, None, None,
                                           'unused', lambda _: None, Path(directory)/'journal.db')
            await controller.run('Solve this: ' + target)
        page.goto.assert_awaited_once_with(target, wait_until='domcontentloaded', timeout=120000)

    async def test_batch_does_not_reopen_starting_skill(self):
        target = 'https://www.deltamath.com/app/student/1/2/start'
        with tempfile.TemporaryDirectory() as directory:
            controller = UnifiedController(None, None, None, None, None, None,
                                           'unused', lambda _: None, Path(directory)/'journal.db')
            controller._run_single = AsyncMock(return_value='Website acceptance observed: 1 question completed.')
            controller.advance_to_next = AsyncMock(return_value=True)
            await controller.run('Solve 2 questions: ' + target)
            calls = controller._run_single.await_args_list
            self.assertIn(target, calls[0].args[0])
            self.assertNotIn(target, calls[1].args[0])
