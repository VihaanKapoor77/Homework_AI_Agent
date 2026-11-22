# Repaired-agent test report

## Full live assignment run — 2026-11-22

- Ran the actual `agent.py` Gradio chat workflow against assignment 35114314, continuing from the linked GCF skill through the remaining skills.
- Final website overview explicitly showed **Chapter 4 #2: Assignment, Complete: 100%; Grade: 100%**. All eight skills were complete: seven at 5/5 and Rotation and Reflection Rules at 100%.
- Finished GCF from 3/5, both trinomial skills from 0/5, and Difference of Perfect Squares (Level 2) from 0/5. The final squares continuation recorded one incorrect attempt before reaching 5/5.
- This was a supervised run with retries, not an uninterrupted autonomous pass. Encountered Gemini 503 failures, request pacing, a transient startup sign-in report, screenshot timeouts, and an overly strict equation-transcription check.
- Updated planner instructions to preserve the displayed equation and leave the equation field empty for factoring expressions. Added bringing the browser tab forward before observation/verification screenshots. Equivalent instructions were passed through the live chat prompt for validation.
- Agent stopped at the final Back to Home control without declaring assignment completion. Opened that observed control separately and verified the completion overview. Automatic final-overview detection remains a limitation.
- Editor diagnostics: no errors after screenshot change. Legacy `test_unified_controller` run: 14 tests, 7 errors (including obsolete `point_reflection_plan` references); no claim that the full unit suite passes.

## Live transformation regression — November 19, 2026

- Reproduced the form incompatibility: Shapes requests a numeric counterclockwise
  angle, while Rigid Motions provides labeled rotation dropdown options.
- Inspected all four Shapes transformation controls and all three Rigid Motions
  controls in both the first and second positions on the actual website.
- Live controller continuation: four consecutive accepted answers, no incorrect
  submissions, Rigid Motions advanced from 1/5 to 5/5. The accepted compositions
  were 180° rotation + left 3; 270° rotation + down 8; x-axis reflection + down 3;
  y-axis reflection + down 3. Shapes was already complete at 5/5.
- Exact math regression: 144 combinations of rotations, both axis reflections,
  four translation directions, and enlargement/reduction factors.
- Form mapping regression: 288 combinations across both numeric-angle and
  rotation-dropdown layouts, including both transformation positions.
- Browser regression exercises all three nonzero quarter-turn angles with all
  four translation directions, plus dynamic reflection/dilation entry.
- Scope: these checks cover the observed composition controls, not every possible
  DeltaMath topic or arbitrary transformation centers. Unknown controls still stop.

## Live timed rotation/reflection round — 2026-11-20

- Tested the actual assigned DeltaMath skill ending `eac45c7373614026750a77bb41f840ef` using the agent's dedicated Chrome session.
- Reproduced the original app failure: it interpreted the Start screen as a question and stopped with "Ambiguous answer-field mapping" after 104.3 seconds, including timeout recovery.
- Added explicit Start handling, extraction of the visible question's KaTeX source without duplicate accessibility text, exact local solving, and verification through score increments. Timer changes do not invalidate the question.
- Live website result after the fix: **10/10, Best Time 1.7 seconds, Grade 100%**. The website explicitly confirmed all required problems were answered.
- Focused regression suite: **30 tests passed**, including live-shaped timed markup and no-submit behavior. Editor diagnostics: no errors in the changed solver/controller modules.
- This validates the rotation/reflection timed skill; it does not establish support for every DeltaMath timed activity.

## Live GCF regression — 2026-11-20

- Tested skill ending `65f1c84a5b3e4196bbc5b725407c7814` in the agent's dedicated Chrome browser.
- Fixed keyboard entry of braced exponents and whitespace that incorrectly moved the MathQuill cursor. Added exact factoring and structural editor readback for the observed Variable Only GCF form.
- Two live answers were marked Correct: `xy^3(x+y^2)` and `xy^3(x^3+y^2)`. Score advanced from 1/5 to 3/5.
- Second submission ran through the restarted `agent.py` Gradio chat endpoint and finished in 10.1 seconds. Initial post-restart request prematurely reported sign-in while the authenticated page was still loading; retry succeeded without signing in again.
- Focused regression: 19 tests passed, including polynomial factoring/keyboard and timed browser fixtures. No editor diagnostics in changed implementation modules.
- An older, separate `test_math_specialist` test could not import its obsolete `MathPlan` API; this unrelated test was not included in the passing focused suite.

## Earlier benchmark details

- Local math benchmark: 241/241 correct (100% on this synthetic test set).
- Solver median latency: 0.759 ms; p95 latency: 3.861 ms; 0.276 sec total CPU/wall measured across these examples.
- Full unittest discovery with local Chromium fixtures: 76 tests run; 71 passed; 5 skipped; 0 failures.
- Twelve local Chromium integration tests cover reading, entering, delayed page rendering, MathQuill interface, dropdown, two solution fields, end-to-end feedback, fractional text input, a y-variable equation and duplicate-attempt prevention; multi-question advancement after acceptance.
- Gradio local smoke test: HTTP 200 on `http://127.0.0.1:7921/`.

The benchmark does not measure network latency, Gemini inference accuracy, nor the actual DeltaMath website. No API key or logged-in DeltaMath session was available. Browser fixture tests are synthetic local DOM pages, **not** live DeltaMath verification.
