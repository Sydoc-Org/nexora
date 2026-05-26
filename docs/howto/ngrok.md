# ngrok setup (SYAPP01)

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
