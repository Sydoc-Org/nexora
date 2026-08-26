# ngrok setup (SYAPP01)

> **Being replaced by Cloudflare Tunnel** — see `docs/howto/cloudflare-tunnel.md`.
> ngrok stays the live entry point until that cutover completes; this doc is
> valid until the ngrok service is uninstalled, then it gets deleted.

Navigate to the ngrok directory:

```powershell
cd /d "D:\sydoc\tools\ngrok"
```

Run manually:

```powershell
ngrok start --config="D:\sydoc\nexora\ngrok.yaml" --all
```

Install and run as a Windows service (run as administrator):

```powershell
ngrok service install --config="D:\sydoc\nexora\ngrok.yaml"
ngrok service start
```
