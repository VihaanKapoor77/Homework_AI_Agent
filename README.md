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
- **Answer entry:** discovers fields in the currently visible DOM, supports regular inputs, MathQuill public API where available, and labeled dropdowns. Multiple roots can add solution fields. Dropdowns use exact visible labels. Readback/visual confirmation occurs before submission. You can request a number of consecutive questions, and the controller advances only after explicit acceptance of each answer.
- **Rate limit:** one shared Gemini request budget, by default **5 calls/minute** (change it to match your actual API quota). It does **not** unnecessarily rate-limit local SymPy calculations or each message you send.
- **Recovery:** browser timeout -> one 60-second delay -> reopen browser and read current state. Submission journal prevents sending the same answer again blindly.
- **Scheduling:** durable SQLite tasks in `~/.assignment-agent/scheduled_tasks.sqlite3`; use `America/New_York` for daylight-saving-aware Eastern time. App and computer must stay running.
- **Examples and lessons:** observed Show Examples steps may be stored locally; method memory helps solve analogous questions with new numbers. Wrong attempts aren't recorded as correct answers.
- **Privacy:** login is done manually. Screenshots sent to Gemini may contain visible page content. Store your API key only in local `.env` and avoid sharing screenshots containing private information.

## Test it

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

Live DeltaMath success rate, browser speed on the real site, and Gemini screenshot accuracy **were not measured** because no authenticated browser or API key is available in this environment. The real site may change its DOM or controls over time.

## Project entry points

- `agent.py`: normal app, Chrome persistence, recovery, scheduling and typed-tool compatibility.
- `unified_controller.py`: single problem workflow, journal, answer safety.
- `math_solver.py`: exact symbolic solver used in a killable subprocess.
- `deltamath_tools.py`, `math_keyboard.py`, `delta_workflow.py`: page inspection and math entry.
- `vision_math.py`, `gemini_client.py`, `gemini_budget.py`: screenshots, API calls, 429 pacing.
- `adaptive_math.py`: reusable methods and observed feedback memory.
- `app.py` and `agent_rate_limited.py`: alternative launchers, same `main()`.

The supplied original ~1,100-line agent is retained in `legacy/agent_original_reference.py` for comparison, but should **not** be used to launch the repaired version.
