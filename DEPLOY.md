# Putting Creative Cut on a server

Creative Cut runs as three containers on one Linux server: the app, PostgreSQL, and Caddy (which handles HTTPS).

## What you need

- A Linux server with Docker. Clipping is CPU work: plan on **8+ CPU cores, 16 GB RAM and 200+ GB of disk** if
  several people will use it. Transcription runs at roughly 10x real time per video on 4 cores.
- A domain name pointing at the server (an `A` record).
- Nothing for AI: on a site with sign-in every person brings their own key (Settings, AI). Optional: a Google "Web application" OAuth client, and an SMTP
  service for emails.

## Steps

1. Copy this folder to the server (or `git clone` it there).
2. `cp .env.example .env` and fill it in: the AI lines, `CREATIVECUT_DOMAIN`, `POSTGRES_PASSWORD`, and
   `COMPOSE_PROFILES=own-https` if the server is Creative Cut's alone. Put key files, if you use files, in `./secrets/`.
3. `docker compose up -d --build`
   The first start downloads the speech model (about 480 MB) and creates the database tables.
4. Open `https://your-domain` and sign up. With Docker, accounts are on (`CREATIVECUT_ACCOUNTS=1`), so everyone signs in.
   Every new account is a normal user.
5. Make yourself an admin, on the server: `docker compose exec app python -m studio.admin grant you@example.com`
   The admin dashboard is then at `https://your-domain/admin`. It answers "not found" for everyone who is not an
   admin, and no page or web request can make someone an admin: only that command can.
6. Every person, you included, opens **Settings, AI**, picks a service (Gemini, OpenAI, Grok, Groq, OpenRouter, Claude or
   a local model), picks a model, pastes their own key and presses Save and test. Their key is used only for their own
   videos and costs you nothing. Without one, their clips are picked by loudness only.
   To pay for everyone's AI yourself instead, put a key in `.env` and set `CREATIVECUT_SHARED_AI=1`.

## Connecting YouTube, Instagram and TikTok

People connect their accounts with one click in **Settings, Connected apps**: they press Connect, sign in on the
platform's own page, and come back. For that, the server needs one app registered with each platform. An admin can
do it right there: press **Set up** on a platform, follow the steps shown, and paste the app's id and secret (or put
them in `.env`, see `.env.example`). The redirect address to register is shown in the panel, with a Copy button.

- **YouTube** (Google Cloud): an OAuth client of type Web application, with YouTube Data API v3 turned on. Until
  Google verifies the app, people see a warning screen and uploads stay private.
- **Instagram** (Meta for Developers): a Business app with Instagram (API setup with Instagram login). Works with
  Creator and Business accounts. Until Meta reviews the app, only accounts added as testers can connect. Instagram
  fetches each clip from a one-hour signed link on your site, so the site needs a public https address.
- **TikTok** (TikTok for Developers): an app with Login Kit and the Content Posting API (Direct Post), scopes
  `user.info.basic` and `video.publish`. Until TikTok audits the app, clips are posted as private (Creative Cut does
  this by itself and says so on the account).

Instagram and TikTok only accept https redirect addresses.

## Google setup (sign-in and YouTube)

In Google Cloud, create an OAuth client of type **Web application** with these redirect URIs:

- `https://your-domain/auth/google/callback`
- `https://your-domain/oauth/youtube/callback`

Enable **YouTube Data API v3** in the same project. Posting publicly to YouTube needs Google's API audit;
until then uploads from the API stay private.

## Email

Set the `CREATIVECUT_SMTP_*` lines and `CREATIVECUT_MAIL_FROM` to send password-reset and confirmation emails through any
SMTP service. On a public site also set `CREATIVECUT_VERIFY_EMAIL=1`, so people confirm their address before clipping.
Without SMTP on an HTTPS site, no reset emails can be sent.

## Good to know

- **Data**: everything lives in two Docker volumes, `pgdata` (accounts, AI usage) and `data` (videos, clips).
  Back both up. `docker compose exec db pg_dump -U creativecut creativecut > backup.sql` dumps the database.
- **Capacity**: `CREATIVECUT_JOB_WORKERS` is how many videos are processed at once; `CREATIVECUT_MAX_LIVE` is how many live
  streams are recorded at once. Raise them only as far as the CPU allows.
- **One server only**: jobs and live recordings run inside the app process. Do not start a second copy of the app
  against the same data.
- **YouTube downloads from data centres** are sometimes refused by YouTube ("confirm you're not a bot"). If links
  fail on the server but work at home, the server's address is the cause. Creative Cut then pauses YouTube links for a
  few minutes and says so; Twitch and Kick links keep working. See "When YouTube refuses the server" below.
- **Updates**: `git pull && docker compose up -d --build`. A restart pauses videos in progress (they pick up
  where they stopped) and live recordings (clips already found are finished from the saved stream).
- **Open sign-up**: anyone who can reach the site can make an account. They use their own AI key, so AI costs you
  nothing, unless you set `CREATIVECUT_SHARED_AI=1`. Keep the limits in `.env` sensible on a public address.

## A server that already runs other sites

Leave `COMPOSE_PROFILES=own-https` out of `.env`. Creative Cut then listens only on `127.0.0.1:8765` and the web
server that is already there forwards the domain to it: see `deploy/nginx-creativecut.conf`, or
`deploy/docker-compose.traefik.yml` for Traefik.

## When YouTube refuses the server

Three things fix most "confirm you're not a bot" errors. Use them in this order.

1. **Keep yt-dlp up to date.** Nothing to do: a newer yt-dlp is fetched into the data folder every 24 hours, and again
   soon after YouTube refuses a download, with no restart. Change how often with `CREATIVECUT_YTDLP_UPDATE_HOURS`
   (0 turns it off). The admin dashboard shows the version in use and the result of the last look.
2. **Give it cookies from a normal YouTube account.**
   - Make a **spare** Google account and sign in to YouTube with it in a private browser window. Do not use your main
     account: YouTube can block an account that is used by a server.
   - Install a cookie-export extension (for example "Get cookies.txt LOCALLY"), open `youtube.com` in that window and
     export `youtube.com` cookies as `cookies.txt`. Then close the private window, without signing out first, so the
     cookies are not invalidated.
   - Copy the file to the server as `secrets/youtube-cookies.txt` and add
     `CREATIVECUT_YT_COOKIES=/secrets/youtube-cookies.txt` to `.env`. Run `docker compose up -d`.
   - Cookies expire after weeks or months. When downloads start failing again, export a fresh file.
   - The file is read only: each download works on a private copy that is deleted afterwards.
3. **Get YouTube videos through Apify** (the way that works on a server). Make an account at apify.com, open
   Settings, Integrations, and create an API token. Add
   `CREATIVECUT_APIFY_TOKEN=apify_api_...` to `.env` (never commit `.env`), then `docker compose up -d`. From then on YouTube
   links are downloaded by the Apify actor `marielise.dev/youtube-video-downloader`, and Creative Cut deletes the video
   as soon as its clips are cut. Apify bills per started minute of video, so set `CREATIVECUT_APIFY_MAX_MIN` (90 by
   default) to the longest video you will pay for; it also caps what one video can cost. Twitch and Kick downloads do
   not use it, and neither do any of the settings above when a token is set.

## Cloudflare CDN in front

With the record proxied (orange cloud):

- Set `CREATIVECUT_CLIENT_IP_HEADER=CF-Connecting-IP` in `.env`, so rate limits see each visitor, not Cloudflare. The
  header is only believed for connections that really come from Cloudflare's address ranges.
- Images, videos and scripts under `/brand/` and `/assets/` are cached by Cloudflare automatically. Signed-in
  pages, clips and the API send `private` or `no-store` and are never cached by Cloudflare.
- Use SSL/TLS mode Full (strict) with a Cloudflare origin certificate in `secrets/` and
  `CREATIVECUT_CADDYFILE=Caddyfile.origin`.

## Speech to text on a graphics card

Optional. A second machine with an NVIDIA card can do most of the transcription much faster:
`deploy/gpu/docker-compose.yml` runs it, and `CREATIVECUT_ASR_URL` plus `CREATIVECUT_ASR_TOKEN` on the main server point
at it. Keep its port closed to the internet. If it is unreachable, the main server carries on with its own
processor.
