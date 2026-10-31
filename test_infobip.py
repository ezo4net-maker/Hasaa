import json, os, subprocess, sys, time, urllib.request, threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
APP_PORT='8766'
FAKE_PORT=8767
DB=ROOT/'tests'/'test_infobip.db'
if DB.exists(): DB.unlink()

class FakeInfobip(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def _json(self, status, data):
        raw=json.dumps(data).encode(); self.send_response(status)
        self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(raw)))
        self.end_headers(); self.wfile.write(raw)
    def do_POST(self):
        if self.headers.get('Authorization') != 'App test-key':
            return self._json(401,{'message':'bad auth'})
        n=int(self.headers.get('Content-Length','0')); body=json.loads(self.rfile.read(n) or b'{}')
        if self.path.startswith('/2fa/2/pin?'):
            assert body['applicationId']=='app-1'
            assert body['messageId']=='msg-1'
            assert body['from']=='Hassa'
            assert body['to']=='249912345678'
            return self._json(200,{'pinId':'PIN-123','to':body['to'],'smsStatus':'MESSAGE_SENT'})
        if self.path=='/2fa/2/pin/PIN-123/verify':
            return self._json(200,{'pinId':'PIN-123','verified': body.get('pin')=='654321','attemptsRemaining':4})
        return self._json(404,{'message':'not found'})

fake=ThreadingHTTPServer(('127.0.0.1',FAKE_PORT),FakeInfobip)
threading.Thread(target=fake.serve_forever,daemon=True).start()

def call(path,method='GET',data=None,headers=None):
    body=None if data is None else json.dumps(data).encode()
    req=urllib.request.Request(f'http://127.0.0.1:{APP_PORT}{path}',data=body,method=method,headers={'Content-Type':'application/json',**(headers or {})})
    with urllib.request.urlopen(req,timeout=5) as r:return r.status,json.loads(r.read())

env=os.environ.copy(); env.update({
    'PORT':APP_PORT,'HASSA_DB':str(DB),'HASSA_DEV_OTP':'0','HASSA_ADMIN_KEY':'test-admin',
    'INFOBIP_API_KEY':'test-key','INFOBIP_BASE_URL':f'http://127.0.0.1:{FAKE_PORT}',
    'INFOBIP_APPLICATION_ID':'app-1','INFOBIP_MESSAGE_ID':'msg-1','INFOBIP_SENDER':'Hassa'
})
p=subprocess.Popen([sys.executable,'server.py'],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
try:
    for _ in range(40):
        try:
            s,d=call('/api/health')
            if s==200: break
        except Exception: time.sleep(.1)
    else: raise RuntimeError('app server did not start')
    assert d['otp_provider']=='infobip' and d['dev_otp'] is False
    s,d=call('/api/auth/request-otp','POST',{'phone':'+249912345678'})
    assert s==200 and d['provider']=='infobip' and 'dev_code' not in d
    s,d=call('/api/auth/verify-otp','POST',{'phone':'+249912345678','code':'654321'})
    assert s==200 and d.get('token')
    print('INFOBIP INTEGRATION TEST PASSED')
finally:
    p.terminate()
    try:p.wait(timeout=3)
    except: p.kill()
    fake.shutdown(); fake.server_close()
