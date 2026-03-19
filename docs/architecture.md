# FormIntellect Architecture

## Layers
- appsscript/ : Google Sheets UI — sidebar, modals, menu
- server/     : FastAPI on localhost:5000 — bridge between Sheets and Python
- engine/     : Pure Python logic — no FastAPI imports, fully testable

## Request flow (Module 1)
Sidebar -> google.script.run -> Code.gs -> UrlFetchApp -> FastAPI route -> engine -> Google Forms

## Why localhost?
No hosting cost, no latency, no auth layer, user data never leaves their machine.

## State management
Submission state is held in memory on the server. Sheet Status column is the source of truth.
Pausing is safe — already-submitted rows are skipped on resume.
