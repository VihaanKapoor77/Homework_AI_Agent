# Repaired-agent test report

- Local math benchmark: 241/241 correct (100% on this synthetic test set).
- Solver median latency: 0.759 ms; p95 latency: 3.861 ms; 0.276 sec total CPU/wall measured across these examples.
- Full unittest discovery with local Chromium fixtures: 76 tests run; 71 passed; 5 skipped; 0 failures.
- Twelve local Chromium integration tests cover reading, entering, delayed page rendering, MathQuill interface, dropdown, two solution fields, end-to-end feedback, fractional text input, a y-variable equation and duplicate-attempt prevention; multi-question advancement after acceptance.
- Gradio local smoke test: HTTP 200 on `http://127.0.0.1:7921/`.

The benchmark does not measure network latency, Gemini inference accuracy, nor the actual DeltaMath website. No API key or logged-in DeltaMath session was available. Browser fixture tests are synthetic local DOM pages, **not** live DeltaMath verification.
