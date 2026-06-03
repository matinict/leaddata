import subprocess, json
from pathlib import Path

def get_media_duration(filepath):
    try:
        cmd = ["ffprobe","-v","error","-show_entries","format=duration","-of","json",str(filepath)]
        r = subprocess.run(cmd,capture_output=True,text=True,timeout=10)
        if r.returncode==0:
            return float(json.loads(r.stdout).get("format",{}).get("duration",0))
    except: pass
    return 0.0
