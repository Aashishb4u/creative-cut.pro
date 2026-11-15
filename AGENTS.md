# Working on Creative Cut

A short map for contributors and AI coding assistants.

## Run and test

- Run: `python -m studio.server` (settings from `.env`; see `.env.example`). Needs Python 3.10+ and `ffmpeg`.
- Speech model, once: `python -m studio.fetch_model`.
- Tests: `python tests/run.py`. It starts a throwaway copy on a spare port with an empty data folder. Run it
  before and after any change to `studio/`. No keys needed.
- To try a risky change by hand without touching real data:
  `CREATIVECUT_DATA=<temp folder> CREATIVECUT_PORT=8766 python -m studio.server`.

## Where things are

| File | What it does |
|---|---|
| `studio/server.py` | Every web route, and the gate that runs before each request (who is asking, limits, headers) |
| `studio/config.py` | Every setting, read from environment variables |
| `studio/ai.py` | The only code that talks to an AI service, and the AI settings saved from the dashboard (`ai.json` in the data folder) |
| `studio/brain.py` | The prompts: finding clips, live judging, hooks and titles, caption fixes |
| `studio/usage.py` | The record of AI calls and tokens shown on the AI usage page |
| `studio/jobs.py` | The video pipeline and the fair queue |
| `studio/live.py` | Live recording and clipping |
| `studio/transcribe.py`, `studio/asr_worker.py` | Speech to text, here or on a second machine |
| `studio/render.py` | Cutting, layouts and captions (ffmpeg and Pillow) |
| `studio/visual.py` | Looks at a clip's picture (movement, shot changes, black or frozen frames) for the viral score |
| `studio/media.py` | Downloading (yt-dlp), probing, audio |
| `studio/auth.py`, `studio/account.py`, `studio/admin.py` | Sign-in, deleting things, the admin dashboard |
| `studio/db.py` | Database tables (SQLAlchemy core; SQLite or PostgreSQL) |
| `web/index.html` | The whole signed-in app, one file, no build step |
| `web/landing.html`, `web/hero3d.js` | The public front page. Its hero has a three.js clip carousel (`web/hero3d.js`, with `web/three-r170.js` kept locally because the security policy only allows scripts from this server). Its own colours and type are in its `:root` block |

## Rules worth knowing

- **Sign-in is off by default** (`config.ACCOUNTS`): every request then belongs to one built-in owner
  (`auth.local_user()`). With `CREATIVECUT_ACCOUNTS=1` it is a normal multi-user site. Both paths are tested.
- **Who is asking** always comes from the session (`ctx.uid()`), never from the request body. Background threads
  set it themselves with `ctx.as_user(...)`.
- **Anything that changes what a user sees must call `ctx.bump()`**. The page polls `/api/sync`, which answers
  from memory when that user's counter has not moved.
- **Text from videos is untrusted**: it goes into prompts through `brain._safe` and out through `brain._text`.
- **Adding an AI provider**: add a row to `PROVIDERS` in `studio/ai.py`. If it speaks the OpenAI chat format that
  is all; otherwise add one function that returns `(parsed JSON, tokens in, tokens out)`.
- **Clips are rendered in a short temporary folder** and moved into place (`render.render_clip`): ffmpeg's caption
  step cannot open paths longer than 260 characters on Windows.
- **Secrets** are read from the environment or from files named by `*_FILE` settings. Never write a key, a real
  address or a personal path into a tracked file.
- **Pages** are plain HTML, CSS and JavaScript. The look is the blue SaaS style: blue `#2563EB` to `#59A4FF` gradient,
  navy `#0B1D4D` text, soft light-blue cards, Montserrat. Shadows are soft and blue-tinted only; hover states change colour.
- **Free plan** (`plan.py`): `CREATIVECUT_FREE_VIDEOS` finished videos per account (default 5) and `CREATIVECUT_CLIPS_PER_VIDEO`
  clips per video (default 3). One video at a time per person; `jobs.cancel` stops one at its next step (`_set` raises `Cancelled`).
- **Space is limited per person** (`storage.py`, `CREATIVECUT_MAX_USER_MB`, 100 by default): over it, their oldest finished videos
  are deleted, never one still being made, recorded, with a post waiting, or just finished.
- **YouTube access**: `media.ytdl_extra` adds the cookies file (a private copy) and proxy for YouTube links only;
  `ytupdate.py` keeps yt-dlp current in the data folder. Never log or print the proxy address.
- **Videos are never kept.** `jobs._drop_source` deletes the downloaded video the moment its clips are cut. Making a clip
  again fetches just its own stretch (`jobs._fetch_again`). There is no file upload: videos come from links only.
- **Viral score**: the AI's score (`ai_score`) is blended once with the picture's score (`brain.blend`, `jobs._look`).
  `brain.NICHES` holds what to look for in each kind of video; `brain.tighten` cuts dead air off a clip's ends.
- Comments and messages are written in plain language for people who do not program. Keep that tone.
