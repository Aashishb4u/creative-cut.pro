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
- **Pages** are plain HTML, CSS and JavaScript. The look is dark violet with a red accent (Montserrat). **Every colour lives in
  `web/theme.css`** as `--c-*` names; pages, the 3D hero, the animated background and the emails read from it, so never type a
  colour into a page. The logo files and favicon in `web/brand/` are pictures: redo them if the brand colour changes.
  `tests/test_theme.py` guards this. Shadows are soft; hover states change colour.
- **Plan** (`plan.py`): `CREATIVECUT_FREE_VIDEOS` free finished videos per account (default 2), then a monthly
  subscription: `CREATIVECUT_PLAN_PRICE_INR` (499) for `CREATIVECUT_PLAN_VIDEOS` (20) videos every 30 days, plus refills
  (`CREATIVECUT_REFILL_*`) that never expire but work only while subscribed. `CREATIVECUT_CLIPS_PER_VIDEO` clips per video
  (default 3). Counts live in `plan.json` in the person's folder. One video at a time per person; `jobs.cancel` stops one
  at its next step (`_set` raises `Cancelled`).
- **Payments** (`billing.py`): Cashfree, as in Commently Reviews: Subscriptions for the monthly plan, Orders for refills.
  Nothing is given from what the browser or a webhook says: the state is always read back from Cashfree. Webhooks need
  Cashfree's signature (client secret). A refill counts once (`payments` row switches to "paid"). The return page
  `/billing/return` takes Cashfree's cross-site POST (the only route let past the origin check). The checkout script is
  the one outside script the security policy allows (`server.CSP`). Keys: `CASHFREE_ENV`, `CASHFREE_CLIENT_ID`,
  `CASHFREE_CLIENT_SECRET`. By hand: `python -m studio.admin month|refill <email>`. Public pages show prices through
  `{{PRICE}}`, `{{PACK_VIDEOS}}`, `{{REFILL_PRICE}}`, `{{REFILL_VIDEOS}}`, `{{CLIPS}}`, `{{FREE}}` (`server._prices`).
- **Space is limited per person** (`storage.py`, `CREATIVECUT_MAX_USER_MB`, 100 by default): over it, their oldest finished videos
  are deleted, never one still being made, recorded, with a post waiting, or just finished.
- **YouTube access**: yt-dlp straight from the server. `media.ytdl_extra` adds the cookies file (a private copy) for YouTube
  links only, and `ytupdate.py` keeps yt-dlp current in the data folder. When YouTube still refuses, the page asks the person
  to upload the video (see below). There is no proxy and no paid download service.
- **Videos are never kept.** `jobs._drop_source` deletes the downloaded video the moment its clips are cut. Making a clip
  again fetches just its own stretch (`jobs._fetch_again`). Videos come from links. The only upload is a fallback: when a link fails, the person downloads the video themselves and uploads it for that same video (pieces to `POST /api/jobs/{id}/upload`, then `/upload/finish`; `CREATIVECUT_UPLOAD_CHUNK_MB`, `CREATIVECUT_MAX_UPLOAD_MB`; deleted like any other source; `cleanup.py` removes unfinished `upload.part` files every morning at 6 IST, from inside the server, no cron needed).
- **The line for videos** (`jobs._FairQueue`): one line per person, taken in turns. `CREATIVECUT_JOB_SHORT_RESERVED` workers are kept for
  videos up to `CREATIVECUT_SHORT_VIDEO_MIN` minutes; a length not yet known counts as long. Waiting people see an estimate
  (`jobs.wait_text`, from how long recent videos took). Over `CREATIVECUT_PICKY_ASR_MIN` minutes a video is not transcribed
  whole: `brain.busy_windows` picks the loudest stretches and only those are transcribed, best first, until there are enough
  clips. In every video, parts after the clips are found are not transcribed.
- **Downloads cannot fill the disk**: every yt-dlp download runs through `media._size_guard` (`CREATIVECUT_MAX_DOWNLOAD_GB`, 8, and
  `CREATIVECUT_MIN_FREE_DISK_GB`, 3). One account once wrote a 116 GB file from a single link and filled the server.
- **Viral score**: the AI's score (`ai_score`) is blended once with the picture's score (`brain.blend`, `jobs._look`).
  `brain.NICHES` holds what to look for in each kind of video; `brain.tighten` cuts dead air off a clip's ends.
- **Search and sharing**: every public page carries the Open Graph and Twitter tags (WhatsApp, Facebook, X, LinkedIn read them), with the
  1200x630 picture `web/brand/og.png` (keep it under 300 KB; WhatsApp drops big ones). Sign-up is indexed; sign-in, reset and `/app` are
  not. A signed-out request for a page that does not exist is a real 404, not "sign in". `/robots.txt` and `/sitemap.xml` come from `server.py`.
- Comments and messages are written in plain language for people who do not program. Keep that tone.
