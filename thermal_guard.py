"""Conservative admission control for local GPU inference requests."""
import subprocess,time

def gpu_temperature():
    result=subprocess.run(['nvidia-smi','--query-gpu=temperature.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=5,creationflags=0x08000000)
    if result.returncode:raise RuntimeError('GPU temperature sensor unavailable; inference paused')
    return float(result.stdout.strip().splitlines()[0])

def wait_until_cool(read=gpu_temperature,sleep=time.sleep,pause_c=80,resume_c=65,abort_c=85,timeout=180):
    if not resume_c<pause_c<abort_c:raise ValueError('Invalid thermal thresholds')
    started=time.monotonic();paused=False;initial=None
    while True:
        temperature=read()
        if initial is None:initial=temperature
        if temperature>=abort_c:raise RuntimeError(f'GPU {temperature:g} C: stop new inference requests')
        if (not paused and temperature<pause_c) or (paused and temperature<=resume_c):
            return {'initial_c':initial,'ready_c':temperature,'paused':paused,'seconds':time.monotonic()-started}
        paused=True
        if time.monotonic()-started>timeout:raise RuntimeError('GPU did not cool; inference paused')
        sleep(2)
