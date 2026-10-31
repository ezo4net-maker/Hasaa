import json, os, subprocess, sys, time, urllib.request, urllib.error
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PORT='8765'
DB=ROOT/'tests'/'test.db'
if DB.exists(): DB.unlink()
env=os.environ.copy();env.update({'PORT':PORT,'HASSA_DB':str(DB),'HASSA_DEV_OTP':'1','HASSA_ADMIN_KEY':'test-admin'})
p=subprocess.Popen([sys.executable,'server.py'],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)

def call(path,method='GET',data=None,headers=None):
    body=None if data is None else json.dumps(data).encode()
    req=urllib.request.Request(f'http://127.0.0.1:{PORT}{path}',data=body,method=method,headers={'Content-Type':'application/json',**(headers or {})})
    with urllib.request.urlopen(req,timeout=5) as r:return r.status,json.loads(r.read())

try:
    for _ in range(30):
        try:
            s,d=call('/api/health')
            if s==200:break
        except Exception:time.sleep(.1)
    else: raise RuntimeError('server did not start')
    s,d=call('/api/providers');assert s==200 and len(d['providers'])>=4
    s,d=call('/api/auth/request-otp','POST',{'phone':'+249912345678'});assert s==200 and d.get('dev_code')
    code=d['dev_code']
    s,d=call('/api/auth/verify-otp','POST',{'phone':'+249912345678','code':code});token=d['token'];assert token
    provider={'phone':'+249912345678','name':'اختبار','business_name':'ورشة اختبار','account_type':'فني / حرفي','profession':'كهربائي','description':'test','area':'بحري','service_areas':['بحري'],'delivery':False,'emergency':True,'available':True,'lat':15.6,'lng':32.5,'services':[{'name':'كشف','price':'1000'}]}
    s,d=call('/api/providers','POST',provider,{'Authorization':'Bearer '+token});assert s==200;pid=d['provider']['id']
    s,d=call('/api/requests','POST',{'customer_name':'عميل','customer_phone':'+249911111111','service':'كشف','provider_id':pid,'lat':15.61,'lng':32.51});assert s==201;rid=d['request_id'];track=d['track_token']
    s,d=call(f'/api/requests/{rid}?token={track}');assert s==200 and d['request']['id']==rid
    s,d=call(f'/api/requests?provider_id={pid}',headers={'Authorization':'Bearer '+token});assert any(x['id']==rid for x in d['requests'])
    s,d=call(f'/api/requests/{rid}/status','POST',{'status':'accepted'},{'Authorization':'Bearer '+token});assert d['status']=='accepted'
    s,d=call('/api/admin/stats',headers={'X-Admin-Key':'test-admin'});assert d['stats']['providers']>=5 and d['stats']['requests']>=1
    print('SMOKE TESTS PASSED')
finally:
    p.terminate()
    try:p.wait(timeout=3)
    except: p.kill()
