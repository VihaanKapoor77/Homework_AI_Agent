import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from unified_controller import UnifiedController


class ControllerRunTests(unittest.IsolatedAsyncioTestCase):
    async def test_resumes_completed_question_without_reopening_initial_link(self):
        with tempfile.TemporaryDirectory() as directory:
            controller=self.make_controller(directory)
            controller._run_single=AsyncMock(side_effect=[
                'Previously completed question: current skill is complete.',
                'Website acceptance observed: 1 question completed.'])
            controller.advance_to_next=AsyncMock(side_effect=[True,False])
            controller.assignment_complete=AsyncMock(return_value=True)
            result=await controller.run('Finish the whole thing https://www.deltamath.com/app/student/1/2/start')
            self.assertNotIn('https://',controller._run_single.await_args_list[1].args[0])
            self.assertIn('1 question(s) completed',result)
            self.assertIn('Whole assignment complete:',result)

    async def test_whole_thing_and_finish_assignment_continue(self):
        for prompt in ('Finish the whole thing','Complete the entire task','Finish this assignment','Do my homework'):
            with self.subTest(prompt=prompt),tempfile.TemporaryDirectory() as directory:
                controller=self.make_controller(directory)
                controller._run_single=AsyncMock(return_value='Website acceptance observed: 1 question completed.')
                controller.advance_to_next=AsyncMock(side_effect=[True,False])
                controller.assignment_complete=AsyncMock(return_value=True)
                result=await controller.run(prompt)
                self.assertEqual(controller._run_single.await_count,2)
                self.assertIn('Whole assignment complete: confirmed',result)

    async def test_missing_next_is_not_assignment_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            controller=self.make_controller(directory)
            controller._run_single=AsyncMock(return_value='Website acceptance observed: 1 question completed.')
            controller.advance_to_next=AsyncMock(return_value=False)
            controller.assignment_complete=AsyncMock(return_value=False)
            result=await controller.run('Finish the whole thing')
            self.assertIn('completion is NOT confirmed',result)
            self.assertNotIn('Whole assignment complete:',result)

    def make_controller(self, directory):
        return UnifiedController(
            None, None, None, None, None, None, 'unused', lambda _: None,
            Path(directory) / 'journal.db',
        )

    async def test_whole_assignment_runs_until_no_next_question(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = self.make_controller(directory)
            controller._run_single = AsyncMock(
                return_value='Website acceptance observed: 1 question completed.'
            )
            controller.advance_to_next = AsyncMock(side_effect=[True, True, False])

            result = await controller.run('Finish the whole DeltaMath assignment')

            self.assertEqual(controller._run_single.await_count, 3)
            self.assertEqual(controller.advance_to_next.await_count, 3)
            self.assertIn('3 question(s) completed', result)

    async def test_all_work_wording_runs_until_no_next_question(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = self.make_controller(directory)
            controller._run_single = AsyncMock(
                return_value='Website acceptance observed: 1 question completed.'
            )
            controller.advance_to_next = AsyncMock(side_effect=[True, False])

            result = await controller.run('Do all of the work')

            self.assertEqual(controller._run_single.await_count, 2)
            self.assertIn('2 question(s) completed', result)

    async def test_finish_counted_questions_runs_requested_count(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = self.make_controller(directory)
            controller._run_single = AsyncMock(
                return_value='Website acceptance observed: 1 question completed.'
            )
            controller.advance_to_next = AsyncMock(return_value=True)

            await controller.run('Finish 3 questions')

            self.assertEqual(controller._run_single.await_count, 3)

    async def test_explicit_question_count_is_not_capped_at_25(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = self.make_controller(directory)
            controller._run_single = AsyncMock(
                return_value='Website acceptance observed: 1 question completed.'
            )
            controller.advance_to_next = AsyncMock(return_value=True)

            result = await controller.run('Solve 26 questions')

            self.assertEqual(controller._run_single.await_count, 26)
            self.assertEqual(controller.advance_to_next.await_count, 25)
            self.assertIn('26 question(s) completed', result)

    async def test_unspecified_request_still_runs_one_question(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = self.make_controller(directory)
            controller._run_single = AsyncMock(
                return_value='Website acceptance observed: 1 question completed.'
            )
            controller.advance_to_next = AsyncMock()

            await controller.run('Solve this question')

            controller._run_single.assert_awaited_once()
            controller.advance_to_next.assert_not_awaited()

    async def test_whole_assignment_moves_on_after_incorrect_answer(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = self.make_controller(directory)
            controller._run_single = AsyncMock(side_effect=[
                'Website reported incorrect. Previous attempt recorded; do not retry unchanged.',
                'Website acceptance observed: 1 question completed.',
            ])
            controller.advance_to_next = AsyncMock(side_effect=[True, False])

            result = await controller.run('Finish the whole DeltaMath assignment')

            self.assertEqual(controller._run_single.await_count, 2)
            self.assertEqual(controller.advance_to_next.await_count, 2)
            self.assertIn('1 question(s) completed', result)
            self.assertIn('1 incorrect question(s) recorded', result)

    async def test_single_question_request_stops_after_incorrect_answer(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = self.make_controller(directory)
            controller._run_single = AsyncMock(
                return_value='Website reported incorrect. Previous attempt recorded; do not retry unchanged.'
            )
            controller.advance_to_next = AsyncMock()

            result = await controller.run('Solve this question')

            controller._run_single.assert_awaited_once()
            controller.advance_to_next.assert_not_awaited()
            self.assertIn('incorrect', result.lower())

    async def test_submission_intent_respects_explicit_opt_out(self):
        self.assertTrue(UnifiedController.submission_requested('Finish the whole assignment'))
        self.assertTrue(UnifiedController.submission_requested('Do all of the work'))
        self.assertFalse(UnifiedController.submission_requested('Solve this, but do not submit'))


if __name__ == '__main__':
    unittest.main()
