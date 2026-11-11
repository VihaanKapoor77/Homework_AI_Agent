# Homework agent(for deltamath)

This agent can do you homework for you.

## Install on Windows

Use Python 3.12 if possible. but any 3.1x should work

to install python run 
```powershell
winget install -e --id Python.Python.3.12
```

1st, download this zip

Then, to set up the agent, run


```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
python agent.py
```

If you already have a virtual environment, activate it instead of making another. If `py -3.12` isn't available, use `py` or `python` for a supported Python version. On some locked-down PowerShell setups, run `.venv\Scripts\python.exe agent.py` directly.`

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




## Project entry points

- `agent.py`: normal app, Chrome persistence, recovery, scheduling and typed-tool compatibility.
- `unified_controller.py`: single problem workflow, journal, answer safety.
- `math_solver.py`: exact symbolic solver used in a killable subprocess.
- `deltamath_tools.py`, `math_keyboard.py`, `delta_workflow.py`: page inspection and math entry.
- `vision_math.py`, `gemini_client.py`, `gemini_budget.py`: screenshots, API calls, 429 pacing.
- `adaptive_math.py`: reusable methods and observed feedback memory.
- `app.py` and `agent_rate_limited.py`: alternative launchers, same `main()`.




