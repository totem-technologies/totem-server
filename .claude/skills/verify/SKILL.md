---
name: verify
description: How to run and visually verify totem-server changes end-to-end (Django in Docker + bun-built front end).
---

# Verifying totem-server changes in the running app

## Launch

1. Docker runs via OrbStack. If the daemon is down: `open -a OrbStack && sleep 8`.
2. Start the stack detached: `docker compose -f local.yml up -d --remove-orphans` (Django on `https://totem.local`, Mailpit UI on `https://mailpit.local/`).
3. Front-end changes are NOT picked up automatically unless the watcher is running — rebuild bundles once with `bun run build:js` (or `bun run build` for CSS too).
4. Dev data: fixtures are usually already loaded. If pages are empty, run `command make fixtures`.

## Finding a page to drive

- Upcoming sessions (anonymous OK): `curl "http://totem.local/api/v1/spaces/?category=&author=&limit=3"` — each item has a `url` like `/spaces/session/<slug>/`. Note `category` and `author` query params are required (empty is fine).
- Session detail API: `GET /api/v1/spaces/event/<slug>`.

## Screenshots / driving the UI

- Playwright's Python package works via a uv `# /// script` with `chromium.launch(channel="chrome")` (uses installed Google Chrome, no browser download).
- Quick one-shot: `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --window-size=1280,1600 --virtual-time-budget=8000 --screenshot=out.png <url>` — works, but the Django Debug Toolbar renders expanded over the right side of the page.
- To collapse the debug toolbar in Playwright: load the page once, `localStorage.setItem('djdt.show', 'false')`, reload (or just `document.getElementById('djDebug')?.remove()`).
- Interactive sidebar on session pages is the `<t-detail-sidebar>` web component; wait for `t-detail-sidebar add-to-calendar-button` or similar inner selectors. The add-to-calendar dropdown renders inside the `<add-to-calendar-button>` element's shadow root.

## Gotchas

- Emails go to Mailpit at `https://mailpit.local/`.
- Tests must run in Docker: `command make test` (never bare pytest); JS-only: `command make test-js`.
