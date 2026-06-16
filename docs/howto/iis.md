# IIS deployment setup

1. Download URL Rewrite: <https://www.iis.net/downloads/microsoft/url-rewrite>
2. Install CGI in Server Manager
3. Install `wfastcgi`:

   ```powershell
   py -m pip install wfastcgi
   cd .\python\scripts
   wfastcgi-enable.exe
   ```

4. Install all modules
5. Add to IIS
6. Edit middleware prefix if necessary

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
