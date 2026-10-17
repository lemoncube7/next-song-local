"""Streaming local inference with active temperature cancellation."""
import json,time,urllib.request,threading
from thermal_guard import gpu_temperature,wait_until_cool

def chat(payload,endpoint='http://127.0.0.1:11434',read_temperature=gpu_temperature,timeout=120):
    admission=wait_until_cool(read=read_temperature)
    body={**payload,'stream':True};req=urllib.request.Request(endpoint+'/api/chat',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    result={};pieces=[];stop=threading.Event();cancelled=[]
    with urllib.request.urlopen(req,timeout=timeout) as response:
        def watch():
            while not stop.wait(.5):
                try:
                    temperature=read_temperature()
                    if temperature>=80:
                        cancelled.append(f'GPU {temperature:g} C: generation cancelled to cool')
                        response.close();return
                except Exception as error:
                    cancelled.append('Temperature monitoring failed: '+str(error));response.close();return
        thread=threading.Thread(target=watch,daemon=True);thread.start()
        try:
            for line in response:
                if cancelled:break
                if not line.strip():continue
                chunk=json.loads(line)
                if chunk.get('error'):raise RuntimeError(chunk['error'])
                pieces.append(chunk.get('message',{}).get('content',''))
                if chunk.get('done'):result=chunk;break
        except Exception:
            if not cancelled:raise
        finally:stop.set();thread.join(6)
    if cancelled:
        # Closing a streaming response cancels this request; no partial identity accepted.
        raise RuntimeError(cancelled[0])
    if not result.get('done'):raise RuntimeError('Incomplete model response')
    result['message']={'content':''.join(pieces)};result['thermal_guard']=admission
    return result
