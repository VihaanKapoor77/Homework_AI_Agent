# DeltaMath study agent — repaired edition

This version replaces overlapping agent loops with **one controller**:

1. Reuse a dedicated Chrome profile and inspect the current question.
2. Solve clear algebra with a safe local SymPy worker (no Gemini requests needed).
3. Use Gemini 3.5 Flash-Lite screenshot interpretation for diagrams/ambiguous notation.
4. Check all roots and map each answer to a visible input/MathQuill field or dropdown.
5. Verify entry before any submission, and report success **only** after explicit website feedback.
6. Preserve a one-shot 60-second timeout recovery, scheduled tasks, worked-example notes, and local method memory.

It doesn't access hidden DeltaMath answer APIs and doesn't bypass authentication or CAPTCHAs. There is no guarantee it can solve every possible DeltaMath question. It is intended as a learning/verification assistant, and only verified, readable answers should be submitted.

## Install on Windows

Use Python 3.11–3.13 if possible. In PowerShell, inside the unzipped project folder:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
python agent.py
```

If you already have a virtual environment, activate it instead of making another. If `py -3.13` isn't available, use `py` or `python` for a supported Python version. On some locked-down PowerShell setups, run `.venv\Scripts\python.exe agent.py` directly.

**Edit `.env`** to replace `YOUR_GEMINI_API_KEY_HERE` with your own key. Do not share the key. If Chrome cannot be found, uncomment and set `CHROME_PATH` to your installed Chrome executable. Keep `HEADLESS=false` if you need to sign in manually.

Open the local Gradio page shown in the terminal, paste the HTTPS DeltaMath assignment URL, or open it yourself in the dedicated Chrome window. **You do not need to run `--login` for every session.** The Chrome profile is kept at `~/.assignment-agent/chrome` (the same path used by the supplied original agent). If authentication expires, sign in manually in that window and try again. You can optionally open a dedicated manual-login window with:

```powershell
python agent.py --login https://www.deltamath.com/
```

Close that separate Chrome window before launching the normal app. Never send passwords or one-time codes to the agent.

## Main features kept or repaired

- **Fast local math:** exact SymPy algebra, real roots with domain exclusions, fractions, logs, factor/expand/differentiate/integrate, perpendicular bisectors; solver executes separately with a timeout.
- **Vision:** sends a screenshot to Gemini for diagram interpretation and unusual answer formatting. Unreadable diagram labels stop the flow rather than invent an answer.
- **Answer entry:** discovers fields in the currently visible DOM, supports regular inputs, MathQuill public API where available, labeled dropdowns, and uniquely matched visible radio choices. Coordinate translations, common origin-based rotations/reflections, and quadrilateral symmetry questions are solved locally from accessible vertex coordinates. Radio labels discard duplicate rendered math text before matching. Explicit solve/answer/do/complete/finish requests submit verified answers unless submission is explicitly declined. Requests such as “do all of the work” run through visible unfinished skills; after an incorrect graded result, a multi-question request may continue only through a unique visible Next Problem control and never retries the same answer automatically.
- **Rate limit:** one shared Gemini request budget, by default **5 calls/minute** (change it to match your actual API quota). It does **not** unnecessarily rate-limit local SymPy calculations or each message you send.
- **Recovery:** browser timeout -> one 60-second delay -> reopen browser and read current state. Submission journal prevents sending the same answer again blindly.
- **Scheduling:** durable SQLite tasks in `~/.assignment-agent/scheduled_tasks.sqlite3`; use `America/New_York` for daylight-saving-aware Eastern time. App and computer must stay running.
- **Examples and lessons:** observed Show Examples steps may be stored locally; method memory helps solve analogous questions with new numbers. Wrong attempts aren't recorded as correct answers.
- **Privacy:** login is done manually. Screenshots sent to Gemini may contain visible page content. Store your API key only in local `.env` and avoid sharing screenshots containing private information.

## Test it

### Continuous completion

For math, use "Solve and don't stop", "Keep going", or "Finish this assignment".
For subject decks, use "Answer the deck and don't stop" or "Complete the whole deck".
Whole-assignment/deck runs have no total request deadline or 300-card cutoff;
explicit multi-question math runs also have no total request deadline.
They continue while progress is possible and only report completion after website
confirmation. Explicit question counts and single-question requests retain their
scope. Stop still cancels a run. Per-operation timeouts, login requirements,
verification failures, and uncertain submissions can still pause work with a reason.

### Whole-assignment continuation (November 13, 2026)

Transformation reading update (November 19, 2026): composition questions now use
the graph's accessible vertex coordinates and exact arithmetic to check both
steps against every corresponding vertex. Supported candidates include rotations,
axis reflections, origin-centered dilations, and axis translations. The controller
re-discovers parameter fields after selecting each transformation, so newly shown
answer controls are not mistaken for a different problem. Unsupported mappings
pause with a coordinate-verification explanation instead of guessing two dropdowns.
Planning and verification capture the full page, and model context includes graph
descriptions. Restart an already-running app to load these changes.

Rigid Motions also uses rotation dropdowns instead of numeric angle inputs. The
controller maps exact angles to the observed clockwise/counterclockwise labels
and checks the selected label rather than confusing it with the option's internal
value. Exact coordinate composition does not require a screenshot to render in a
minimized browser.

Live validation: Shapes is confirmed complete at 5/5. The repaired controller
completed all four remaining Rigid Motions questions correctly, from 1/5 to 5/5,
including 180-degree and 270-degree rotations and reflections over both axes.
This does not establish whole-assignment completion. See [test results](TEST_RESULTS.md).

Requests such as "Finish the whole thing", "Complete the entire task", and
"Finish this assignment" now continue across questions and unfinished skills,
including earlier skills in the sidebar. Explicit single-question/count requests
keep their original scope. Previously completed questions can be resumed without
reopening the initial skill or submitting them again.

The controller reports whole-assignment completion only when the website shows
all listed skills complete or an explicit assignment-complete message. Missing
navigation, expired login, uncertain feedback, and verification failures report
a pause rather than completion. The chat also labels that result "Paused after".

Validation: 51 targeted tests passed, followed by 28 focused checks after the
final resume/login changes. Live app testing recognized whole-assignment mode,
but the saved DeltaMath login had expired, so live completion could not be verified.

### Piecewise graph repair (November 12, 2026)

Linear piecewise functions now use rendered MathML and exact arithmetic to draw
segments and rays, set open/closed endpoints, and verify the rendered lines before
submission. Supported endpoints must lie on visible integer grid points. Ambiguous,
nonlinear, offscreen, or already-populated graphs stop with an explanation.
This path makes no model calls. A pasted DeltaMath link now opens the requested
skill even when another DeltaMath page is already open; subsequent questions keep
their normal navigation. Chat shows elapsed-time updates during longer operations.
An explicit Send button shares the Enter-key handler and Stop cancellation. A real
Chromium UI check clicked Send and received the correct English answer, `geese`,
in 4.4 seconds. A science request through the running app API returned carbon
dioxide in 4.0 seconds.

Authenticated live checks on the supplied Graphing Piecewise Functions (Level 1)
skill produced **3 accepted answers and no incorrect submissions**, advancing its
score from 0/5 to 3/5. The first check took 8.5 seconds; the next two together took
13.8 seconds, including browser startup and navigation. These are individual live
measurements, not a guarantee for every problem or network connection.

The final focused regression run executed 150 tests: **145 passed, 5 skipped**,
including real local Chromium tests for math and subject entry. Seven real-model
Spanish, English, science, and social-studies examples passed. Full discovery before
the repair also exposed 10 pre-existing failures/errors in obsolete compatibility
tests (removed action helpers, GeminiBudget, MathPlan, and old entry expectations);
those legacy tests were not rewritten or counted as passing.

`test_piecewise_graph.py` covers exact slopes, finite intervals, endpoint types,
rejection of unsupported domains, and incorrect graph readback.
`test_request_navigation.py` covers switching assignment links and preserving batch
navigation. `live_piecewise_check.py URL solve N` repeats an opt-in authenticated
check through the normal controller and submits up to N answers; omit `solve N`
for inspection only.

Run code-level tests with no key:

```powershell
python -m unittest discover -v -p "test_*.py"
python benchmark.py
```

For local Chromium tests (no network or DeltaMath login required), set `TEST_CHROME_PATH` if Playwright can't find a browser. In PowerShell:

```powershell
$env:RUN_BROWSER_TESTS='1'
$env:TEST_CHROME_PATH='C:\Program Files\Google\Chrome\Application\chrome.exe'
python -m unittest discover -v -p "test_*.py"
```

The **legacy HTTPS-route browser fixtures** are intentionally skipped because this test environment blocks outbound DeltaMath requests; the corresponding local Chromium fixtures are enabled with `RUN_BROWSER_TESTS=1`. The obsolete LangGraph test is also skipped because the legacy looping graph was removed. Both conditions are transparent, not claimed as passing tests.

### Test evidence from this environment

- **241/241 generated local math cases correct** (linear, quadratic, exact fractions, domain restrictions, and no-real-root cases).
- Local math solver median **0.759 ms**, 95th percentile **3.861 ms**. This excludes process startup, reading web pages, network calls and model inference.
- **76 unit/integration tests run: 71 passed, 5 skipped** (12 local real-Chromium DOM/controller tests were included).
- Local Gradio UI smoke test returned **HTTP 200**.

The figures above describe the earlier local test run. Subsequent authenticated live checks confirmed a DeltaMath submission and a Boom vocabulary matching card. These individual checks do not establish a general success rate. The real sites may change their controls over time.

## Project entry points

### Subjects and translation

The Subject menu adds **Spanish / Translation**, **English**, **Social studies**,
**Science**, and **General**. Examples:

- `Translate: Estoy cansado hoy.`
- `Spanish: Why is it soy estudiante but estoy cansado?`
- `English: Correct this sentence and explain the change: ...`
- `Science: Explain photosynthesis.`
- `Solve the visible card` after opening a Boom Learning activity link.

Subject questions use a separate planner and independent second model check.
Missing passages, uncertain interpretations and disagreements stop automatic entry.
The second check reduces errors; it is not a guarantee of correctness or a web search.
Supply the passage or sources when the question needs them.

Boom support answers one verified card per request and can move through instruction
cards first. Sign in manually in the dedicated Chrome window. Translation requests
are read-only. Unsupported controls and other websites return suggestions rather
than clicking unknown targets. Unknown grading results stop further attempts.

DeltaMath URLs always use the original math controller, regardless of the Subject
selection. Choose **Math / DeltaMath** to switch back without pasting a link.
Subject attempts use a separate journal and do not alter the math attempt history.

Spanish compound cards enter the verb and select the full DOCTOR/PLACE category
before submitting. Category validation distinguishes Origin (the first O) from
Occupation (the second O), and Position from Location. A screenshot check verifies
the completed form. Missing category selections and disconnected activity pages
stop submission. Matching cards also receive a completed-layout check.

Latest targeted regression run: 67 tests, 63 passed and 4 skipped, including local
Chromium subject and DeltaMath checks. Seven real-model subject examples also passed.
Live Boom testing also returned **Correct!** for `El hombre está leyendo` after
entering `está`, selecting **A / Action** in PLACE, verifying the completed form,
and clicking Submit. Position/Location and both DOCTOR O tiles have local regression
coverage; this live result specifically verifies the Action card.

Run `python -m unittest test_subject_solver -v` for subject validation/routing tests.

The category-ID repair resolves an explicitly named DOCTOR/PLACE category to its
observed tile before independent verification. It preserves missing-layout,
ambiguous-category, and submission guards. Live testing on November 13, 2026
observed **Correct!** for `estoy / Condition` ("Yo ___ muy enfermo hoy") and
`son / Origin` ("They are from India"). Local validation passed 24 subject tests
(including Chromium fixtures) and 33 math/navigation/runtime regression tests.

With `RUN_BROWSER_TESTS=1`, run `test_subject_browser` and `test_controller_browser`
for subject and DeltaMath browser regressions. `python live_subject_benchmark.py`
runs seven small real-model examples (uses API quota; does not submit to a website).

- `agent.py`: normal app, Chrome persistence, recovery, scheduling and typed-tool compatibility.
- `unified_controller.py`: single problem workflow, journal, answer safety.
- `math_solver.py`: exact symbolic solver used in a killable subprocess.
- `deltamath_tools.py`, `math_keyboard.py`, `delta_workflow.py`: page inspection and math entry.
- `vision_math.py`, `gemini_client.py`, `gemini_budget.py`: screenshots, API calls, 429 pacing.
- `adaptive_math.py`: reusable methods and observed feedback memory.
- `app.py` and `agent_rate_limited.py`: alternative launchers, same `main()`.

The supplied original ~1,100-line agent is retained in `legacy/agent_original_reference.py` for comparison, but should **not** be used to launch the repaired version.
