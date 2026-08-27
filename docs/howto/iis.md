# IIS deployment setup (SYAPP01)

nexora runs as **one `waitress` process managed by IIS's HttpPlatformHandler**.
IIS owns the port/TLS binding and the app-pool lifecycle; HttpPlatformHandler
starts `D:\sydoc\tools\py\python.exe -m waitress ... nx_main:app` on a
loopback port it picks (`%HTTP_PLATFORM_PORT%`) and reverse-proxies every
request to it. Everything is declared in `web.config` at the site root — nothing
is configured in IIS Manager beyond the site pointing at `D:\sydoc\nexora`.
(`wfastcgi` served until v3.2.3; it is archived upstream and handled one blocking
request per process.)

## One-time host setup

1. **HttpPlatformHandler v1.2 (x64)** — <https://www.iis.net/downloads/microsoft/httpplatformhandler>.
   Verify in an elevated PowerShell:

   ```powershell
   Import-Module WebAdministration
   Get-WebGlobalModule | Where-Object Name -eq httpPlatformHandler
   ```

2. **waitress on the prod interpreter** — it is in `requirements.txt`, and the
   deploy workflow's `pip install -r requirements.txt` installs it; by hand:

   ```powershell
   D:\sydoc\tools\py\python.exe -m pip install waitress
   ```

3. Site → physical path `D:\sydoc\nexora`, app pool `DefaultAppPool`.
   The app-pool identity must be able to write `D:\sydoc\nexora\var\`
   (waitress stdout log, sessions, CSV request logs) — same as before.

The deploy workflow (`.github/workflows/deploy.yml`, step *Preflight IIS host*)
checks 1 and 2 **before** stopping the app pool, so a forgotten install aborts
the deploy while the old app is still serving instead of 500-ing the site.

## What `web.config` sets, and why

| Setting | Why |
| --- | --- |
| `--listen=127.0.0.1:%HTTP_PLATFORM_PORT%` | IIS is the only client; LAN can't bypass it. |
| `--threads=32` | Matches the SQLAlchemy pools (10 + 20 overflow per engine). |
| `--connection-limit=1000` | Keep-alive channels from ~500 browsers would hit waitress's default ceiling of 100. |
| `--url-scheme=https` | TLS terminates at the ngrok edge; waitress only ever sees plain HTTP. Telling it "https" keeps Talisman's `force_https` from redirect-looping and makes `url_for(_external=True)` right. |
| `--trusted-proxy=127.0.0.1 --trusted-proxy-headers=x-forwarded-for` | waitress ≥ 2 **strips** `X-Forwarded-*` from untrusted peers. IIS is the peer, so trust it — otherwise the CSV log and the rate limiter see only `127.0.0.1`. The limiter keys on the leftmost hop (`nx_lib/extensions.py::client_ip`). |
| `ENVIRONMENT=PROD`, `PYTHONPATH=D:\sydoc\nexora` | Child-process env; the app pool identity has no user profile to inherit from. |
| `stdoutLogFile=…\var\logs\system\waitress-stdout` | Process stdout/stderr (startup tracebacks land here). `app.log` beside it is the app logger. |
| `requestTimeout=00:02:00` | Same 120 s ceiling the FastCGI setup had. |

URL prefix: IIS forwards the full `/nexora/...` path; `nx_lib/middleware.py`
`PrefixMiddleware` strips it (unchanged). There are deliberately **no URL Rewrite
rules** — a rewrite to `nx_main.py` would reach waitress as a 404.

`tests/unit/test_iis_hosting.py` guards these load-bearing bits.

## Troubleshooting

- **500.19** on every URL → the `httpPlatformHandler` module isn't installed
  (step 1).
- **502.3 / "process failed to start"** → waitress died inside
  `startupTimeLimit` (60 s). Read the newest
  `D:\sydoc\nexora\var\logs\system\waitress-stdout_*.log` — it holds the
  Python traceback (missing package, bad env, DB unreachable at import).
- **Restart** the app = recycle `DefaultAppPool`; HttpPlatformHandler kills and
  relaunches waitress with it. `rapidFailsPerMinute` (default 10) stops
  relaunch attempts for the rest of the minute after a crash loop.
- **Rollback** → `git revert` the commit that changed `web.config` and redeploy.
  `wfastcgi` is still installed on the box; nothing else needs undoing.

## Scaling beyond one process

Threads share the GIL, so CPU-heavy requests (matplotlib chart renders for
scheduled reports) serialise. If a load test shows that, the knobs in order:
raise `--threads`; run 2–4 waitress processes on fixed ports behind IIS ARR
(sessions must then move off the filesystem backend and the limiter needs a
`storage_uri`); only then a second box.

## Per-feature driver requirements

Some features require binary Python packages that are not pure-Python and must be
installed separately on the prod interpreter after the deploy mirrors the code:

- **MS02 Postgres integration** (`nx_lib/workitem_sources.py` / `nx_lib/clients.py`):
  the Postgres driver is not bundled in the repo. Install it on SYAPP01 once:

  ```powershell
  D:\sydoc\tools\py\python.exe -m pip install psycopg2-binary
  ```

  Until installed, `engine_ms02_pg` stays `None` and the MS02 source degrades
  silently (workitems shows only the default SQL Server client; no 500 errors).

- **PDF page rendering** (`nx_lib/octo.py`): the workitem viewer rasterises PDF
  document media (e.g. MS02 `MobScn` pages) to images via `pypdfium2`, a single
  binary wheel (no system Poppler/Ghostscript). Install it on SYAPP01 once:

  ```powershell
  D:\sydoc\tools\py\python.exe -m pip install pypdfium2
  ```

  Until installed, PDF media degrades silently (`pdf_page_count` returns 0, so
  PDF-backed pages just don't appear; image/TIFF pages are unaffected).
