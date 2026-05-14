# Implementation Plan — danalyze

---

## Scripted / Agent-UAT Mode

### Intent

**Original request (paraphrased):**
> Add a capability for agent coding assistants to do some of the UAT. The app should be startable in a special mode where a list of inputs is provided as arguments. The app loads, sends the inputs one by one, renders the screen after each, and writes the rendered frames to stdout. After the final frame the app quits. Text input is provided as a plain string; key events as `"key.<name>"` (e.g. `"key.enter"`, `"key.down"`).

**Interpretation:**

When a coding agent (or a human running automated checks) wants to verify TUI behaviour, they currently have to launch the real app and interact with it manually. This feature makes that programmable: the caller supplies a JSON list of inputs on the command line, the app processes them in sequence (headless — no terminal takeover), and for each input it writes a plain-text rendering of the full screen to stdout. The output can be read directly by an agent or piped into a script.

The feature is *not* a test harness — it runs real production code paths (real scanner, real state machine, real overlay logic). Its outputs are what the user would actually see, captured as text, one frame per input.

**Input format:**
- `"key.<name>"` — simulate pressing a named key: `key.enter`, `key.up`, `key.down`, `key.left`, `key.right`, `key.r`, `key.escape`, `key.backspace`, `key.q`, `key.w`, `key.s`, etc.
- Any other string — type each character of the string in sequence (useful for entering note text or filenames in overlays).

**Output format (stdout):**
```
--- key.down ---
<full plain-text screen, width×height characters, including overlays>

--- [my note] ---
<next frame>

--- key.enter ---
<next frame>
```

One `--- <input> ---` header followed by the rendered frame per input. Frames are produced *after* all synchronous handlers and any background workers (e.g. scan) have completed for that input.

**Run mode:** when `--script` is supplied the app runs headless (`app.run(headless=True, size=(120, 40))`), so the TUI never touches the controlling terminal and the stdout frames are the only output.

**Screen capture:** uses the same compositing pipeline as Textual's built-in `export_screenshot()` — `screen._compositor.render_update()` printed to a Rich `Console` and exported as plain text via `console.export_text()`. This captures the full composited screen including correct side-by-side layout, overlays, and highlights.

---

## Research Findings

Key discoveries made while exploring the codebase and Textual internals before writing this plan. These findings directly shaped the design decisions above.

### 1. Textual version is 8.2.5
Confirmed via `uv run python -c "import textual; print(textual.__version__)"`. The APIs used in this plan (`_compositor`, `render_update`, `App.run(headless, size)`) are all present in this version.

### 2. `export_screenshot()` reveals the correct screen-capture pipeline
Inspecting the source of `App.export_screenshot()` showed exactly how Textual composes a full-screen render:

```python
screen_render = self.screen._compositor.render_update(
    full=True, screen_stack=self.app._background_screens
)
console.print(screen_render)
return console.export_svg(...)
```

We reuse this pipeline verbatim and swap `export_svg()` for `export_text()`. This is preferable to lower-level alternatives (e.g. `Screen.render_lines(crop: Region)`, or iterating widget `render()` calls) because it captures the full composited screen — correct side-by-side layout, overlays, selection highlight — in one shot.

### 3. Rich `Console.export_text()` produces clean plain text
Verified with a live test: a Rich `Console` constructed with `record=True, no_color=True, force_terminal=False` accumulates output and `export_text()` returns it as a plain string with no ANSI escape codes. This is exactly what agent consumers need.

### 4. `App.run()` accepts `headless=True` and `size=(w, h)`
Confirmed from source inspection. Running headless prevents Textual from writing anything to the controlling terminal while our scripted worker writes frames to stdout. Passing an explicit `size` ensures the screen dimensions are known and stable for every frame (no dependency on the real terminal size).

### 5. BINDING keys and `on_key` keys are two separate dispatch paths
Reading `tui/app.py` carefully reveals a critical split:

- **BINDING keys** (`up`, `down`, `left`, `right`, `r`) → Textual resolves these through the `BINDINGS` table and calls the corresponding `action_*` method. They do **not** pass through `on_key`.
- **Everything else** (`enter`, `q`, `w`, `s`, `escape`, `backspace`, character keys) → handled exclusively in `on_key`.

There is no overlap. The scripted dispatcher therefore needs two branches: direct action calls for BINDING keys, and `await self.on_key(events.Key(...))` for all others. Trying to route all keys through `on_key` would silently drop navigation; routing all through actions would miss overlay logic.

### 6. `workers.wait_for_complete()` is already used in TUI tests
The existing test suite (e.g. `test_r_key_scan_shows_sizes`) already calls `await app.workers.wait_for_complete()` to block until scan workers finish. This confirms it is the correct and stable API to use in `_run_script()` to ensure a worker-triggering key (like `r`) has fully completed before the frame is captured.

### 7. `Pilot` is test-only; production scripted mode must drive the app from within
`Pilot` (the Textual testing helper used in `run_test()`) is only available inside an `async with app.run_test()` context. It cannot be used in production. The scripted worker must live inside the app itself (as a Textual worker launched from `on_mount`) and drive inputs by calling action methods and `on_key` directly.

### 8. `_compositor` is private but intentionally accessible
`App.export_screenshot()` — a stable public method — calls `self.screen._compositor` directly. Using the same attribute in `_capture_screen_as_text()` follows Textual's own precedent. If Textual ever renames or removes it, `export_screenshot()` would break too, making it easy to detect.

---

## Phase 1: Input Parsing Utilities [done]

**Files created/modified:**
- `danalyze/script_runner.py` (new)
- `tests/test_script_runner.py` (new)

**Scope:**
Two pure functions with no I/O:
- `parse_script_arg(json_str: str) -> list[str]` — parses the raw CLI value as a JSON array of strings; raises `ValueError` on bad JSON or if the top-level value is not a list of strings.
- `classify_input(s: str) -> tuple[Literal["key", "text"], str]` — `"key.enter"` → `("key", "enter")`; anything else → `("text", s)`.

**Tests (must be red before implementation):**
- `test_parse_valid_list` — `'["key.enter", "[my note]"]'` → `["key.enter", "[my note]"]`
- `test_parse_empty_list` — `'[]'` → `[]`
- `test_parse_invalid_json_raises` — `"not json"` raises `ValueError`
- `test_parse_non_list_raises` — `'"hello"'` (valid JSON, wrong type) raises `ValueError`
- `test_parse_list_with_non_string_raises` — `'["ok", 42]'` raises `ValueError`
- `test_classify_key_enter` — `"key.enter"` → `("key", "enter")`
- `test_classify_key_down` — `"key.down"` → `("key", "down")`
- `test_classify_key_r` — `"key.r"` → `("key", "r")`
- `test_classify_text_string` — `"[my note]"` → `("text", "[my note]")`
- `test_classify_single_char` — `"a"` → `("text", "a")`
- `test_classify_empty_string` — `""` → `("text", "")`

**Automated UAT:** none — pure logic, no observable TUI behaviour at this step.

**Commit message template:** `feat: add script_runner module for scripted-mode input parsing`

---

## Phase 2: CLI `--script` Argument [done]

**Files created/modified:**
- `danalyze/__main__.py`
- `tests/test_cli.py`

**Dependencies:** Phase 1

**Scope:**
- Add `--script JSON` to argparse (type `str`, default `None`).
- After `parse_args`, if `--script` is present call `parse_script_arg()`; on `ValueError` print a clear message to stderr and `sys.exit(1)`.
- Pass `scripted_inputs: list[str] | None` to `DiskAnalyzerApp`.
- When `scripted_inputs` is not `None`, call `app.run(headless=True, size=(120, 40))` instead of `app.run()`.

**Tests (must be red before implementation):**
- `test_script_flag_valid_json_accepted` — no exit when `--script` is a well-formed list of strings
- `test_script_flag_invalid_json_exits` — malformed JSON → `SystemExit` with non-zero code
- `test_script_flag_non_list_exits` — `'"hello"'` → `SystemExit`
- `test_script_arg_none_by_default` — no `--script` → `scripted_inputs=None` on app
- `test_script_uses_headless_run` — `--script` given → `app.run` called with `headless=True` (mock `DiskAnalyzerApp`)
- `test_no_script_uses_normal_run` — no `--script` → `app.run` called without `headless=True`

**Automated UAT:** none — app runs headless so there is no visible TUI output to verify at this step.

**Commit message template:** `feat: add --script flag for headless scripted-mode execution`

---

## Phase 3: Full-Screen Plain-Text Capture [done]

**Files created/modified:**
- `danalyze/tui/app.py`
- `tests/test_script_tui.py` (new)

**Dependencies:** none (independent of Phases 1–2)

**Scope:**
Add `_capture_screen_as_text(self) -> str` to `DiskAnalyzerApp`. Uses the same compositing pipeline as `export_screenshot()` but exports plain text:

```python
def _capture_screen_as_text(self) -> str:
    import io
    from rich.console import Console
    width, height = self.size
    buf = io.StringIO()
    console = Console(
        width=width, height=height, file=buf,
        force_terminal=False, record=True, no_color=True,
    )
    screen_render = self.screen._compositor.render_update(
        full=True, screen_stack=self.app._background_screens
    )
    console.print(screen_render)
    return console.export_text()
```

This captures the full composited screen — correct side-by-side layout, overlays, selection highlight — as clean plain text.

**Tests (all use `app.run_test(size=(80, 24))`):**
- `test_capture_contains_infobar_stats` — text contains "Total:" and "Free:"
- `test_capture_contains_child_names` — text contains all child filenames from the test tree
- `test_capture_with_note_overlay_open` — after `press("enter")`, captured text contains overlay content
- `test_capture_with_quit_overlay_open` — after `press("q")`, captured text contains quit prompt text
- `test_capture_lines_fit_width` — every line in captured text is ≤ specified terminal width

**Automated UAT:** none — the method is an internal helper; end-to-end proof is in Phase 5.

**Commit message template:** `feat: add _capture_screen_as_text for headless screen rendering`

---

## Phase 4: Scripted Execution Worker

**Files created/modified:**
- `danalyze/tui/app.py`
- `tests/test_script_tui.py`

**Dependencies:** Phases 1, 3

**Scope:**

Add `scripted_inputs: list[str] | None = None` parameter to `DiskAnalyzerApp.__init__`, stored as `self._scripted_inputs`.

In `on_mount()`, schedule the scripted worker immediately when inputs are present:
```python
if self._scripted_inputs is not None:
    self.set_timer(0, self._run_script)
```

Add `_run_script()` as an `@work(exclusive=True)` async method:
```python
async def _run_script(self) -> None:
    for input_str in (self._scripted_inputs or []):
        await self._dispatch_scripted_input(input_str)
        await asyncio.sleep(0)                  # yield — let sync handlers fire
        await self.workers.wait_for_complete()  # wait for scan workers etc.
        text = self._capture_screen_as_text()
        sys.stdout.write(f"\n--- {input_str} ---\n{text}\n")
        sys.stdout.flush()
    self.exit()
```

Add `_dispatch_scripted_input(self, input_str: str) -> None` (async):
- Call `classify_input(input_str)` → `("key", name)` or `("text", text)`
- For **key** inputs, dispatch directly to avoid reconstructing Textual internals:
  - `"up"` → `self.action_nav_up()`
  - `"down"` → `self.action_nav_down()`
  - `"left"` → `self.action_nav_left()`
  - `"right"` → `await self.action_nav_right()`
  - `"r"` → `self.action_scan()`
  - all others → `await self.on_key(events.Key(key=name, character=name if len(name) == 1 else None))`
- For **text** inputs, type each character: `await self.on_key(events.Key(key=c, character=c))`

**Tests (use `app.run_test()` with `scripted_inputs` set; stdout captured via `capsys`):**
- `test_scripted_key_down_changes_selected_index` — `["key.down"]` → `app._state.selected_index == 1`
- `test_scripted_key_down_twice` — `["key.down", "key.down"]` → `selected_index == 2`
- `test_scripted_key_enter_opens_overlay` — `["key.enter"]` → `NoteOverlay` is mounted
- `test_scripted_text_types_into_overlay` — `["key.enter", "hello", "key.enter"]` → note saved with text "hello"
- `test_scripted_exit_after_all_inputs` — app exits cleanly after processing all inputs
- `test_scripted_stdout_has_n_frames` — N inputs → N `--- ... ---` separators appear in stdout
- `test_scripted_r_key_waits_for_scan` — `["key.r"]` → frame shows numeric sizes (not `---`), confirming scan completed before capture
- `test_scripted_empty_list_exits_immediately` — `[]` → app exits, no frames written to stdout

**Automated UAT (all runnable as pytest tests):**
1. `["key.down"]` — frame 1 shows second child highlighted; first child is not
2. `["key.down", "key.down"]` — 2 frames; frame 2 highlights third child
3. `["key.enter", "test note", "key.enter"]` — frame 3 contains `"test note"` inline in the file tree
4. `["key.q", "key.y"]` — app exits without error; stdout has exactly 2 frames
5. `["key.r"]` — frame shows numeric sizes not `---` (scan completed before capture)

**Commit message template:** `feat: add scripted execution worker with per-input screen capture to stdout`

---

## Phase 5: End-to-End CLI Wiring Tests

**Files created/modified:**
- `tests/test_script_e2e.py` (new)

**Dependencies:** Phases 1, 2, 3, 4

**Scope:**
Verify the full pipeline from `main()` call through to app construction and execution. Uses `tmp_path` pytest fixture for real-filesystem tests and mocks where appropriate.

**Tests:**
- `test_main_script_flag_wires_inputs_to_app` — call `main(["--script", '["key.down"]', str(tmp_path)])`, mock `DiskAnalyzerApp.run`, verify app constructed with `scripted_inputs=["key.down"]`
- `test_main_script_invalid_json_exits` — `main(["--script", "bad-json"])` → `SystemExit` non-zero
- `test_main_without_script_scripted_inputs_is_none` — no `--script` → app constructed with `scripted_inputs=None`
- `test_main_script_runs_headless` — `--script` given → `run(headless=True)` called (mock `DiskAnalyzerApp`)
- `test_main_script_full_run_writes_stdout` — full integration: real `InMemoryFilesystem`, `DiskAnalyzerApp` with `scripted_inputs=["key.down"]`, verify stdout contains one frame with expected child name

**Automated UAT (runnable as pytest, use `InMemoryFilesystem` + `tmp_path`):**
1. Build a known dir (`/root/apple`, `/root/zebra`), run with `["key.down"]`, verify frame 2 shows `zebra` highlighted
2. Run with `["key.enter", "important", "key.enter", "key.w", "<tmpfile>", "key.enter"]`, verify the CSV is written with the note

**Commit message template:** `feat: end-to-end tests for --script CLI wiring and full scripted-mode run`

---

## Dependency Graph

```
Phase 1 (parser)
  ├── Phase 2 (CLI arg)  ──────────────────────┐
  │                                            ├── Phase 5 (E2E)
  └── Phase 4 (worker) ← Phase 3 (capture) ───┘
```

Phases 2 and 3 can be built in parallel after Phase 1. Phase 4 requires both. Phase 5 requires all preceding phases.

---

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| CLI format | `--script '["key.down", "[text]"]'` | Single JSON array argument; agent-friendly; fully validated before app starts |
| Run mode | `app.run(headless=True, size=(120, 40))` | No terminal takeover; stdout frames are the only output |
| Screen capture | `_compositor.render_update` + Rich `export_text()` | Same pipeline as `export_screenshot`; captures full layout including overlays |
| Key dispatch | Direct action calls for BINDING keys; `self.on_key(events.Key(...))` for all others | Avoids constructing Key events for keys routed through actions; correct for overlay keys |
| Worker wait | `await workers.wait_for_complete()` after every input | Handles `key.r` scan automatically without special-casing |
| Frame separator | `--- <input_str> ---` | Human- and agent-readable; easy to split on in post-processing |
