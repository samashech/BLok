"""Exercise real native-message framing over an owner-only socket with a fake browser."""
import json,os,socket,struct,subprocess,tempfile,threading,time
from pathlib import Path
root=Path(__file__).resolve().parent.parent
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
        print('PASS: native-message framing, request/response IDs and private socket permissions')
    finally:
        process.terminate();process.wait(timeout=3)
