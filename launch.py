"""Open the running app, or start it without installing dependencies."""
import json, subprocess, sys, urllib.request, webbrowser
from pathlib import Path
url='http://127.0.0.1:8765'
try:
    with urllib.request.urlopen(url+'/api/stats',timeout=2) as r:state=json.load(r)
    if state.get('app')=='local-karaoke-v1':
        webbrowser.open(url);sys.exit(0)
except Exception:pass
subprocess.run([sys.executable,'-X','utf8',str(Path(__file__).with_name('server.py')),'--open'],check=False)
