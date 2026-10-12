"""Exercise real native-message framing over an owner-only socket with a fake browser."""
import json,os,socket,struct,subprocess,tempfile,threading,time,sys
from pathlib import Path
from unittest.mock import patch
root=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root))
from hyprash.browser import request as browser_request, BrowserTaskError
with tempfile.TemporaryDirectory() as tmp:
    process=subprocess.Popen(['/usr/bin/python',str(root/'scripts/browser_host.py')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,env={**os.environ,'XDG_RUNTIME_DIR':tmp})
    try:
        path=Path(tmp)/'hyprash-browser.sock'
        for _ in range(100):
            if path.exists():break
            time.sleep(.02)
        assert path.exists()
        assert path.stat().st_mode & 0o777 == 0o600
        result={}
        def request():
            with socket.socket(socket.AF_UNIX) as sock:
                sock.connect(str(path));sock.sendall(b'{"action":"search","site":"youtube","query":"games"}\n')
                result.update(json.loads(sock.makefile('rb').readline()))
        thread=threading.Thread(target=request);thread.start()
        length=struct.unpack('=I',process.stdout.read(4))[0]
        message=json.loads(process.stdout.read(length))
        assert message['site']=='youtube' and message['query']=='games'
        response=json.dumps({'id':message['id'],'result':{'message':'Searched youtube for games'}}).encode()
        process.stdin.write(struct.pack('=I',len(response))+response);process.stdin.flush()
        thread.join(3);assert result['result']['message']=='Searched youtube for games'
        progress=[];result.clear()
        def streamed_request():
            with patch.dict(os.environ,{'XDG_RUNTIME_DIR':tmp}):
                result.update(browser_request({'action':'new_tab'},on_progress=progress.append))
        thread=threading.Thread(target=streamed_request);thread.start()
        length=struct.unpack('=I',process.stdout.read(4))[0]
        message=json.loads(process.stdout.read(length));assert message['progress'] is True
        for fields in [{'progress':{'message':'Checking the new tab','status':'running'}}, {'result':{'message':'Opened a new tab','verified':True,'trace':[{'kind':'verify','status':'complete'}]}}]:
            payload=json.dumps({'id':message['id'],**fields}).encode()
            process.stdin.write(struct.pack('=I',len(payload))+payload);process.stdin.flush()
        thread.join(3);assert not thread.is_alive()
        assert progress[0]['message']=='Checking the new tab'
        assert result['verified'] is True and result['trace'][0]['status']=='complete'
        errors=[]
        def failed_request():
            with patch.dict(os.environ,{'XDG_RUNTIME_DIR':tmp}):
                try:browser_request({'action':'play'})
                except BrowserTaskError as error:errors.append(error)
        thread=threading.Thread(target=failed_request);thread.start()
        length=struct.unpack('=I',process.stdout.read(4))[0];message=json.loads(process.stdout.read(length))
        payload=json.dumps({'id':message['id'],'error':'Playback not confirmed','trace':[{'kind':'verify','status':'failed'}]}).encode()
        process.stdin.write(struct.pack('=I',len(payload))+payload);process.stdin.flush()
        thread.join(3);assert not thread.is_alive()
        assert errors[0].trace[0]['status']=='failed'
        print('PASS: native framing, private socket, legacy response, streamed progress, verified result and failure trace')
    finally:
        process.terminate();process.wait(timeout=3)
