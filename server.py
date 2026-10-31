#!/usr/bin/env python3
import json, os, re, secrets, sqlite3, hashlib, time, mimetypes, urllib.request, urllib.error
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_volume_dir = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "").strip()
_default_db = Path(_volume_dir) / "hassa.db" if _volume_dir else ROOT / "hassa.db"
DB_PATH = Path(os.environ.get("HASSA_DB", os.environ.get("LUQANI_DB", str(_default_db))))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DEV_OTP = os.environ.get("HASSA_DEV_OTP", os.environ.get("LUQANI_DEV_OTP", "1")) == "1"
ADMIN_KEY = os.environ.get("HASSA_ADMIN_KEY", os.environ.get("LUQANI_ADMIN_KEY", "demo-admin"))
PORT = int(os.environ.get("PORT", "8080"))
PHONE_RE = re.compile(r"^\+?[0-9]{9,15}$")

INFOBIP_API_KEY = os.environ.get("INFOBIP_API_KEY", "").strip()
INFOBIP_BASE_URL = os.environ.get("INFOBIP_BASE_URL", "").strip().rstrip("/")
INFOBIP_APPLICATION_ID = os.environ.get("INFOBIP_APPLICATION_ID", "").strip()
INFOBIP_MESSAGE_ID = os.environ.get("INFOBIP_MESSAGE_ID", "").strip()
INFOBIP_SENDER = os.environ.get("INFOBIP_SENDER", "InfoSMS").strip() or "InfoSMS"
INFOBIP_TIMEOUT = float(os.environ.get("INFOBIP_TIMEOUT", "10"))

def infobip_configured():
    return all([INFOBIP_API_KEY, INFOBIP_BASE_URL, INFOBIP_APPLICATION_ID, INFOBIP_MESSAGE_ID])

STATUS_FLOW = ["pending", "accepted", "preparing", "on_the_way", "delivered"]

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()

def connect_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with connect_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS otp_requests(
          phone TEXT PRIMARY KEY,
          code_hash TEXT NOT NULL,
          expires_at INTEGER NOT NULL,
          attempts INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS sessions(
          token TEXT PRIMARY KEY,
          phone TEXT NOT NULL,
          expires_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS providers(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          phone TEXT NOT NULL UNIQUE,
          name TEXT NOT NULL,
          business_name TEXT NOT NULL,
          account_type TEXT NOT NULL,
          profession TEXT NOT NULL,
          description TEXT DEFAULT '',
          area TEXT NOT NULL,
          service_areas TEXT NOT NULL DEFAULT '[]',
          delivery INTEGER NOT NULL DEFAULT 0,
          emergency INTEGER NOT NULL DEFAULT 0,
          available INTEGER NOT NULL DEFAULT 1,
          verified INTEGER NOT NULL DEFAULT 0,
          lat REAL,
          lng REAL,
          profile_image TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS services(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          provider_id INTEGER NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
          name TEXT NOT NULL,
          price TEXT NOT NULL DEFAULT 'حسب الاتفاق'
        );
        CREATE TABLE IF NOT EXISTS requests(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          customer_name TEXT NOT NULL,
          customer_phone TEXT NOT NULL,
          service TEXT NOT NULL,
          note TEXT DEFAULT '',
          provider_id INTEGER REFERENCES providers(id) ON DELETE SET NULL,
          status TEXT NOT NULL DEFAULT 'pending',
          lat REAL,
          lng REAL,
          driver_lat REAL,
          driver_lng REAL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          track_token TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_providers_prof ON providers(profession, available);
        CREATE INDEX IF NOT EXISTS idx_requests_provider ON requests(provider_id, created_at);
        """)
        otp_cols={r["name"] for r in db.execute("PRAGMA table_info(otp_requests)").fetchall()}
        if "provider" not in otp_cols:
            db.execute("ALTER TABLE otp_requests ADD COLUMN provider TEXT NOT NULL DEFAULT 'local'")
        if "pin_id" not in otp_cols:
            db.execute("ALTER TABLE otp_requests ADD COLUMN pin_id TEXT")
        cols={r["name"] for r in db.execute("PRAGMA table_info(requests)").fetchall()}
        if "track_token" not in cols:
            db.execute("ALTER TABLE requests ADD COLUMN track_token TEXT")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_requests_track_token ON requests(track_token) WHERE track_token IS NOT NULL")
        count = db.execute("SELECT COUNT(*) c FROM providers").fetchone()["c"]
        if count == 0:
            seed = [
              ("+249110000001","أحمد علي","مركز بحري للكهرباء","فني / حرفي","كهربائي","صيانة وتمديدات كهربائية","بحري",'["بحري","شمبات"]',0,1,1,1,15.6508,32.5355,"⚡",[('كشف وصيانة','حسب المعاينة')]),
              ("+249110000002","محمد حسن","ورشة النيل","فني / حرفي","ميكانيكي","ميكانيكا عامة وخدمة طوارئ","شمبات",'["شمبات","بحري"]',0,1,1,1,15.6760,32.5160,"🚗",[('فحص ميكانيكي','من 10,000 ج.س')]),
              ("+249110000003","عثمان يوسف","غاز شمبات","مورد","بائع غاز","توصيل أسطوانات الغاز حسب المتوفر","شمبات",'["شمبات","الحلفايا"]',1,1,1,1,15.6810,32.5230,"🔥",[('أسطوانة غاز','حسب المتوفر')]),
              ("+249110000004","سارة محمد","بقالة الخير","تاجر / محل","بقالة","مواد غذائية وتوصيل","بحري",'["بحري"]',1,0,0,1,15.6440,32.5360,"🛒",[('طلب بقالة','حسب الفاتورة')])
            ]
            for row in seed:
                phone,name,business,atype,profession,desc,area,areas,delivery,emergency,available,verified,lat,lng,icon,services = row
                ts=now_iso()
                cur=db.execute("""INSERT INTO providers(phone,name,business_name,account_type,profession,description,area,service_areas,delivery,emergency,available,verified,lat,lng,profile_image,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(phone,name,business,atype,profession,desc,area,areas,delivery,emergency,available,verified,lat,lng,icon,ts,ts))
                pid=cur.lastrowid
                db.executemany("INSERT INTO services(provider_id,name,price) VALUES(?,?,?)",[(pid,n,p) for n,p in services])

def row_to_provider(db, row):
    d=dict(row)
    d["service_areas"] = json.loads(d.get("service_areas") or "[]")
    d["available"] = bool(d["available"]); d["verified"] = bool(d["verified"])
    d["delivery"] = bool(d["delivery"]); d["emergency"] = bool(d["emergency"])
    d["services"]=[dict(x) for x in db.execute("SELECT id,name,price FROM services WHERE provider_id=? ORDER BY id",(d["id"],)).fetchall()]
    return d

def valid_phone(phone):
    return bool(PHONE_RE.match((phone or "").replace(" ", "")))

def auth_phone(headers):
    auth=headers.get("Authorization","")
    if not auth.startswith("Bearer "): return None
    token=auth[7:].strip()
    with connect_db() as db:
        row=db.execute("SELECT phone,expires_at FROM sessions WHERE token=?",(token,)).fetchone()
        if not row or row["expires_at"] < int(time.time()): return None
        return row["phone"]

def infobip_phone(phone: str) -> str:
    # Infobip examples use E.164 digits without the leading plus sign.
    return phone.replace(" ", "").lstrip("+")

def infobip_post(path: str, payload: dict) -> dict:
    if not infobip_configured():
        raise RuntimeError("إعدادات Infobip غير مكتملة")
    url = f"{INFOBIP_BASE_URL}{path}"
    raw = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=raw, method="POST",
        headers={
            "Authorization": f"App {INFOBIP_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "HassaMVP/2.2",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=INFOBIP_TIMEOUT) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body or "{}")
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode("utf-8") or "{}")
            message = detail.get("requestError", {}).get("serviceException", {}).get("text") or detail.get("message") or str(detail)
        except Exception:
            message = str(e)
        raise RuntimeError(f"Infobip رفض الطلب ({e.code}): {message}") from e
    except urllib.error.URLError as e:
        raise RuntimeError("تعذر الاتصال بخدمة Infobip") from e

def infobip_send_pin(phone: str) -> str:
    payload = {
        "applicationId": INFOBIP_APPLICATION_ID,
        "messageId": INFOBIP_MESSAGE_ID,
        "from": INFOBIP_SENDER,
        "to": infobip_phone(phone),
    }
    out = infobip_post("/2fa/2/pin?ncNeeded=false", payload)
    pin_id = str(out.get("pinId") or "").strip()
    if not pin_id:
        raise RuntimeError("Infobip لم يرجع pinId")
    return pin_id

def infobip_verify_pin(pin_id: str, code: str) -> bool:
    out = infobip_post(f"/2fa/2/pin/{pin_id}/verify", {"pin": code})
    return bool(out.get("verified"))

class Handler(SimpleHTTPRequestHandler):
    server_version = "HassaMVP/2.2"
    def translate_path(self, path):
        parsed=urlparse(path).path
        rel=parsed.lstrip("/") or "index.html"
        target=(ROOT/rel).resolve()
        if ROOT not in target.parents and target != ROOT:
            return str(ROOT/"index.html")
        return str(target)
    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt%args))
    def _json(self, status, data):
        raw=json.dumps(data,ensure_ascii=False).encode("utf-8")
        self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Content-Length",str(len(raw))); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(raw)
    def _body(self):
        try:
            size=int(self.headers.get("Content-Length","0"))
            if size>2_500_000: raise ValueError("request too large")
            return json.loads(self.rfile.read(size) or b"{}")
        except Exception as e:
            raise ValueError("JSON غير صالح أو الحجم كبير") from e
    def _admin(self):
        return secrets.compare_digest(self.headers.get("X-Admin-Key",""), ADMIN_KEY)
    def do_GET(self):
        p=urlparse(self.path); path=p.path; q=parse_qs(p.query)
        if path=="/api/health": return self._json(200,{"ok":True,"db":str(DB_PATH.name),"dev_otp":DEV_OTP,"otp_provider":"local" if DEV_OTP else ("infobip" if infobip_configured() else "unconfigured")})
        if path=="/api/providers":
            search=(q.get("q",[""])[0] or "").strip(); profession=(q.get("profession",[""])[0] or "").strip(); available=q.get("available",[""])[0]
            sql="SELECT * FROM providers WHERE 1=1"; args=[]
            if search: sql += " AND (name LIKE ? OR business_name LIKE ? OR profession LIKE ? OR area LIKE ? OR description LIKE ?)"; args += [f"%{search}%"]*5
            if profession and profession!="الكل": sql += " AND profession=?"; args.append(profession)
            if available=="1": sql += " AND available=1"
            sql += " ORDER BY available DESC, verified DESC, id DESC LIMIT 100"
            with connect_db() as db: rows=[row_to_provider(db,r) for r in db.execute(sql,args).fetchall()]
            return self._json(200,{"providers":rows})
        m=re.fullmatch(r"/api/providers/(\d+)",path)
        if m:
            with connect_db() as db:
                row=db.execute("SELECT * FROM providers WHERE id=?",(int(m.group(1)),)).fetchone()
                if not row:return self._json(404,{"error":"مقدم الخدمة غير موجود"})
                return self._json(200,{"provider":row_to_provider(db,row)})
        if path=="/api/requests":
            provider_id=q.get("provider_id",[None])[0]; customer=q.get("customer_phone",[None])[0]
            sql="SELECT r.*,p.business_name,p.profession FROM requests r LEFT JOIN providers p ON p.id=r.provider_id WHERE 1=1"; args=[]
            if provider_id:
                phone=auth_phone(self.headers)
                if not phone:return self._json(401,{"error":"يلزم تسجيل مقدم الخدمة"})
                with connect_db() as db:
                    own=db.execute("SELECT id FROM providers WHERE phone=?",(phone,)).fetchone()
                    if not own or own["id"]!=int(provider_id):return self._json(403,{"error":"غير مصرح"})
                sql+=" AND r.provider_id=?";args.append(int(provider_id))
            if customer: sql+=" AND r.customer_phone=?";args.append(customer)
            sql+=" ORDER BY r.id DESC LIMIT 100"
            with connect_db() as db: rows=[dict(r) for r in db.execute(sql,args).fetchall()]
            return self._json(200,{"requests":rows})
        m=re.fullmatch(r"/api/requests/(\d+)",path)
        if m:
            rid=int(m.group(1)); supplied_token=(q.get("token",[""])[0] or "")
            with connect_db() as db:
                row=db.execute("SELECT r.*,p.business_name,p.profession,p.phone provider_phone FROM requests r LEFT JOIN providers p ON p.id=r.provider_id WHERE r.id=?",(rid,)).fetchone()
                if not row:return self._json(404,{"error":"الطلب غير موجود"})
                allowed=False
                if supplied_token and row["track_token"] and secrets.compare_digest(supplied_token,row["track_token"]): allowed=True
                phone=auth_phone(self.headers)
                if phone and row["provider_id"]:
                    own=db.execute("SELECT phone FROM providers WHERE id=?",(row["provider_id"],)).fetchone()
                    if own and own["phone"]==phone: allowed=True
                if self._admin(): allowed=True
                if not allowed:return self._json(403,{"error":"رابط متابعة الطلب غير صالح"})
                out=dict(row);out.pop("track_token",None)
                return self._json(200,{"request":out})
        if path=="/api/admin/stats":
            if not self._admin():return self._json(401,{"error":"مفتاح الإدارة غير صحيح"})
            with connect_db() as db:
                stats={"providers":db.execute("SELECT COUNT(*) c FROM providers").fetchone()["c"],"verified":db.execute("SELECT COUNT(*) c FROM providers WHERE verified=1").fetchone()["c"],"available":db.execute("SELECT COUNT(*) c FROM providers WHERE available=1").fetchone()["c"],"requests":db.execute("SELECT COUNT(*) c FROM requests").fetchone()["c"],"open_requests":db.execute("SELECT COUNT(*) c FROM requests WHERE status!='delivered' AND status!='cancelled'").fetchone()["c"]}
                providers=[row_to_provider(db,r) for r in db.execute("SELECT * FROM providers ORDER BY id DESC LIMIT 50").fetchall()]
                requests=[dict(r) for r in db.execute("SELECT r.*,p.business_name FROM requests r LEFT JOIN providers p ON p.id=r.provider_id ORDER BY r.id DESC LIMIT 50").fetchall()]
            return self._json(200,{"stats":stats,"providers":providers,"requests":requests})
        return super().do_GET()
    def do_POST(self):
        path=urlparse(self.path).path
        try: data=self._body()
        except ValueError as e:return self._json(400,{"error":str(e)})
        if path=="/api/auth/request-otp":
            phone=(data.get("phone") or "").replace(" ","")
            if not valid_phone(phone):return self._json(400,{"error":"رقم الهاتف غير صالح"})
            exp=int(time.time())+300
            if DEV_OTP:
                code=f"{secrets.randbelow(1000000):06d}"
                with connect_db() as db:
                    db.execute("INSERT INTO otp_requests(phone,code_hash,expires_at,attempts,provider,pin_id) VALUES(?,?,?,0,'local',NULL) ON CONFLICT(phone) DO UPDATE SET code_hash=excluded.code_hash,expires_at=excluded.expires_at,attempts=0,provider='local',pin_id=NULL",(phone,hash_code(code),exp))
                return self._json(200,{"ok":True,"expires_in":300,"message":"تم إنشاء رمز تحقق تجريبي","dev_code":code,"provider":"local"})
            if not infobip_configured():
                return self._json(503,{"error":"OTP الإنتاج غير مهيأ. أضف إعدادات Infobip المطلوبة"})
            try:
                pin_id=infobip_send_pin(phone)
            except RuntimeError as e:
                return self._json(502,{"error":str(e)})
            with connect_db() as db:
                db.execute("INSERT INTO otp_requests(phone,code_hash,expires_at,attempts,provider,pin_id) VALUES(?,?,?,0,'infobip',?) ON CONFLICT(phone) DO UPDATE SET code_hash=excluded.code_hash,expires_at=excluded.expires_at,attempts=0,provider='infobip',pin_id=excluded.pin_id",(phone,hash_code('infobip:'+pin_id),exp,pin_id))
            return self._json(200,{"ok":True,"expires_in":300,"message":"تم إرسال رمز التحقق عبر SMS","provider":"infobip"})
        if path=="/api/auth/verify-otp":
            phone=(data.get("phone") or "").replace(" ",""); code=str(data.get("code") or "").strip()
            if not code:return self._json(400,{"error":"أدخل رمز التحقق"})
            with connect_db() as db:
                row=db.execute("SELECT * FROM otp_requests WHERE phone=?",(phone,)).fetchone()
                if not row or row["expires_at"]<int(time.time()):return self._json(400,{"error":"الرمز منتهي أو غير موجود"})
                if row["attempts"]>=5:return self._json(429,{"error":"محاولات كثيرة. اطلب رمزاً جديداً"})
                provider=row["provider"] if "provider" in row.keys() else "local"
                verified=False
                if provider=="infobip":
                    if not row["pin_id"]: return self._json(400,{"error":"بيانات تحقق Infobip غير مكتملة. اطلب رمزاً جديداً"})
                    try:
                        verified=infobip_verify_pin(row["pin_id"],code)
                    except RuntimeError as e:
                        return self._json(502,{"error":str(e)})
                else:
                    verified=secrets.compare_digest(row["code_hash"],hash_code(code))
                if not verified:
                    db.execute("UPDATE otp_requests SET attempts=attempts+1 WHERE phone=?",(phone,))
                    return self._json(400,{"error":"رمز التحقق غير صحيح"})
                token=secrets.token_urlsafe(32); exp=int(time.time())+60*60*24*30
                db.execute("DELETE FROM otp_requests WHERE phone=?",(phone,));db.execute("INSERT INTO sessions(token,phone,expires_at) VALUES(?,?,?)",(token,phone,exp))
            return self._json(200,{"ok":True,"token":token,"phone":phone})
        if path=="/api/providers":
            phone=auth_phone(self.headers)
            if not phone:return self._json(401,{"error":"تحقق من رقم الهاتف أولاً"})
            if (data.get("phone") or "").replace(" ","") != phone:return self._json(403,{"error":"رقم الحساب لا يطابق رقم التحقق"})
            required=["name","business_name","account_type","profession","area"]
            if any(not str(data.get(x) or "").strip() for x in required):return self._json(400,{"error":"أكمل البيانات الأساسية"})
            img=data.get("profile_image") or None
            if img and len(img)>1_200_000:return self._json(413,{"error":"الصورة كبيرة جداً"})
            ts=now_iso(); areas=json.dumps(data.get("service_areas") or [data["area"]],ensure_ascii=False)
            vals=(phone,str(data["name"]).strip(),str(data["business_name"]).strip(),str(data["account_type"]).strip(),str(data["profession"]).strip(),str(data.get("description") or "")[:600],str(data["area"]).strip(),areas,int(bool(data.get("delivery"))),int(bool(data.get("emergency"))),int(bool(data.get("available",True))),float(data["lat"]) if data.get("lat") is not None else None,float(data["lng"]) if data.get("lng") is not None else None,img,ts,ts)
            with connect_db() as db:
                old=db.execute("SELECT id FROM providers WHERE phone=?",(phone,)).fetchone()
                if old:
                    pid=old["id"]
                    db.execute("""UPDATE providers SET name=?,business_name=?,account_type=?,profession=?,description=?,area=?,service_areas=?,delivery=?,emergency=?,available=?,lat=?,lng=?,profile_image=?,updated_at=? WHERE id=?""",vals[1:-2]+(ts,pid))
                    db.execute("DELETE FROM services WHERE provider_id=?",(pid,))
                else:
                    cur=db.execute("""INSERT INTO providers(phone,name,business_name,account_type,profession,description,area,service_areas,delivery,emergency,available,lat,lng,profile_image,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",vals);pid=cur.lastrowid
                services=data.get("services") or []
                cleaned=[]
                for s in services[:30]:
                    name=str(s.get("name") or "").strip(); price=str(s.get("price") or "حسب الاتفاق").strip()
                    if name: cleaned.append((pid,name[:120],price[:120]))
                if cleaned: db.executemany("INSERT INTO services(provider_id,name,price) VALUES(?,?,?)",cleaned)
                row=db.execute("SELECT * FROM providers WHERE id=?",(pid,)).fetchone();provider=row_to_provider(db,row)
            return self._json(200,{"ok":True,"provider":provider})
        m=re.fullmatch(r"/api/providers/(\d+)/availability",path)
        if m:
            phone=auth_phone(self.headers)
            if not phone:return self._json(401,{"error":"يلزم تسجيل الدخول"})
            pid=int(m.group(1)); available=int(bool(data.get("available")))
            with connect_db() as db:
                own=db.execute("SELECT phone FROM providers WHERE id=?",(pid,)).fetchone()
                if not own or own["phone"]!=phone:return self._json(403,{"error":"غير مصرح"})
                db.execute("UPDATE providers SET available=?,updated_at=? WHERE id=?",(available,now_iso(),pid))
            return self._json(200,{"ok":True,"available":bool(available)})
        if path=="/api/requests":
            name=str(data.get("customer_name") or "").strip(); phone=str(data.get("customer_phone") or "").replace(" ",""); service=str(data.get("service") or "").strip(); provider_id=data.get("provider_id")
            if not name or not valid_phone(phone) or not service:return self._json(400,{"error":"أدخل الاسم ورقم هاتف صالح والخدمة"})
            ts=now_iso();track_token=secrets.token_urlsafe(18)
            with connect_db() as db:
                if provider_id and not db.execute("SELECT id FROM providers WHERE id=?",(provider_id,)).fetchone():return self._json(404,{"error":"مقدم الخدمة غير موجود"})
                cur=db.execute("INSERT INTO requests(customer_name,customer_phone,service,note,provider_id,status,lat,lng,created_at,updated_at,track_token) VALUES(?,?,?,?,?,'pending',?,?,?,?,?)",(name,phone,service,str(data.get("note") or "")[:600],provider_id,float(data["lat"]) if data.get("lat") is not None else None,float(data["lng"]) if data.get("lng") is not None else None,ts,ts,track_token));rid=cur.lastrowid
            return self._json(201,{"ok":True,"request_id":rid,"track_token":track_token,"status":"pending"})
        m=re.fullmatch(r"/api/requests/(\d+)/status",path)
        if m:
            phone=auth_phone(self.headers)
            if not phone:return self._json(401,{"error":"يلزم تسجيل مقدم الخدمة"})
            rid=int(m.group(1)); status=str(data.get("status") or "")
            if status not in STATUS_FLOW+["cancelled"]:return self._json(400,{"error":"حالة الطلب غير صالحة"})
            with connect_db() as db:
                row=db.execute("SELECT r.provider_id,p.phone FROM requests r LEFT JOIN providers p ON p.id=r.provider_id WHERE r.id=?",(rid,)).fetchone()
                if not row or row["phone"]!=phone:return self._json(403,{"error":"غير مصرح"})
                db.execute("UPDATE requests SET status=?,updated_at=? WHERE id=?",(status,now_iso(),rid))
            return self._json(200,{"ok":True,"status":status})
        m=re.fullmatch(r"/api/requests/(\d+)/driver-location",path)
        if m:
            phone=auth_phone(self.headers)
            if not phone:return self._json(401,{"error":"يلزم تسجيل مقدم الخدمة"})
            try: lat=float(data["lat"]);lng=float(data["lng"])
            except:return self._json(400,{"error":"إحداثيات غير صالحة"})
            with connect_db() as db:
                row=db.execute("SELECT p.phone FROM requests r LEFT JOIN providers p ON p.id=r.provider_id WHERE r.id=?",(int(m.group(1)),)).fetchone()
                if not row or row["phone"]!=phone:return self._json(403,{"error":"غير مصرح"})
                db.execute("UPDATE requests SET driver_lat=?,driver_lng=?,updated_at=? WHERE id=?",(lat,lng,now_iso(),int(m.group(1))))
            return self._json(200,{"ok":True})
        m=re.fullmatch(r"/api/admin/providers/(\d+)/verify",path)
        if m:
            if not self._admin():return self._json(401,{"error":"مفتاح الإدارة غير صحيح"})
            verified=int(bool(data.get("verified",True)))
            with connect_db() as db: db.execute("UPDATE providers SET verified=?,updated_at=? WHERE id=?",(verified,now_iso(),int(m.group(1))))
            return self._json(200,{"ok":True,"verified":bool(verified)})
        return self._json(404,{"error":"المسار غير موجود"})

def main():
    init_db()
    os.chdir(ROOT)
    print(f"Hassa MVP v2.2 running on http://0.0.0.0:{PORT}")
    print(f"DB: {DB_PATH}")
    print(f"DEV OTP: {'ON' if DEV_OTP else 'OFF'} | OTP provider: {'local' if DEV_OTP else ('infobip' if infobip_configured() else 'unconfigured')} | Admin key: {ADMIN_KEY if ADMIN_KEY else '[unset]'}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

if __name__=="__main__": main()
