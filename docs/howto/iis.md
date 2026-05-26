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
