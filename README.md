# هسّع — MVP v2.2

نسخة Full-stack تجريبية: واجهة JavaScript/HTML/CSS، خادم Python 3، وقاعدة SQLite. تم ربط مسار OTP مع **Infobip 2FA SMS API** مع الإبقاء على وضع تطوير محلي لا يحتاج أي مزود خارجي.

## التشغيل المحلي السريع

```bash
cd hassa-mvp-v2
python3 server.py
```

ثم افتح:

`http://localhost:8080`

> لا تفتح `index.html` مباشرة، لأن التطبيق يحتاج الخادم وقاعدة البيانات.

## الموجود في النسخة

- بحث الزبون عن مقدمي الخدمات والتجار.
- تفاصيل مقدم الخدمة، خدماته وأسعاره.
- تسجيل مقدم خدمة/تاجر واختيار المهنة مع «مهنة أخرى».
- صورة شخصية/شعار، GPS، مناطق الخدمة، وحالة «متاح الآن».
- SQLite حقيقية، جلسات دخول، وBearer tokens.
- إنشاء الطلبات وتتبع حالتها وموقع السائق.
- إشعارات Browser Notifications تجريبية.
- لوحة إدارة وتوثيق مقدمي الخدمات.
- PWA shell مبدئي.
- OTP محلي للاختبار + **Infobip 2FA حقيقي للإنتاج**.

## وضع OTP المحلي

افتراضياً:

```bash
HASSA_DEV_OTP=1 python3 server.py
```

في هذا الوضع يرجع الخادم رمز OTP للواجهة لتسهيل الاختبار فقط. **لا تستخدمه في النشر العام.**

## ربط Infobip للإنتاج

Infobip 2FA يحتاج أربع قيم أساسية:

1. `INFOBIP_BASE_URL` — Base URL الخاص بحسابك.
2. `INFOBIP_API_KEY` — API Key بصلاحيات 2FA المناسبة.
3. `INFOBIP_APPLICATION_ID` — معرف تطبيق 2FA.
4. `INFOBIP_MESSAGE_ID` — معرف قالب رسالة SMS الذي يحتوي على `{{pin}}`.

اختياري:

- `INFOBIP_SENDER` — اسم المرسل. في التجربة قد تستخدم `InfoSMS` حسب إعداد حسابك.
- `INFOBIP_TIMEOUT` — مهلة الاتصال بالثواني، الافتراضي 10.

انسخ ملف الإعدادات النموذجي:

```bash
cp .env.example .env
```

الخادم لا يقرأ `.env` تلقائياً حتى لا نضيف مكتبة خارجية. صدّر القيم في البيئة أو استخدم منصة الاستضافة لإدخال Environment Variables. مثال Linux/macOS:

```bash
export HASSA_DEV_OTP=0
export HASSA_ADMIN_KEY='ضع-مفتاح-إدارة-قوي'
export INFOBIP_BASE_URL='https://xxxxx.api.infobip.com'
export INFOBIP_API_KEY='YOUR_KEY'
export INFOBIP_APPLICATION_ID='YOUR_APP_ID'
export INFOBIP_MESSAGE_ID='YOUR_MESSAGE_ID'
export INFOBIP_SENDER='InfoSMS'
python3 server.py
```

### إعداد Infobip مرة واحدة

داخل Infobip:

1. أنشئ 2FA Application لاستخدام «تسجيل مستخدمي هسّع».
2. اضبط مدة PIN وعدد المحاولات وحدود الإرسال المناسبة.
3. أنشئ SMS Message Template يحتوي مثلاً على: `رمز التحقق في هسّع هو {{pin}}`.
4. احتفظ بـ Application ID وMessage ID.
5. أنشئ API Key بصلاحيات 2FA اللازمة.
6. ضع القيم في متغيرات البيئة أعلاه.
7. اجعل `HASSA_DEV_OTP=0`.

عندها endpoint `/api/auth/request-otp` يرسل PIN عبر Infobip ولا يعيده للمتصفح، و`/api/auth/verify-otp` يتحقق من PIN لدى Infobip باستخدام `pinId` المحفوظ مؤقتاً في SQLite.

## متغيرات البيئة

- `PORT` — المنفذ، الافتراضي 8080.
- `HASSA_DB` — مسار SQLite.
- `HASSA_DEV_OTP` — 1 للتجربة المحلية، 0 لـInfobip.
- `HASSA_ADMIN_KEY` — مفتاح لوحة الإدارة.
- `INFOBIP_BASE_URL` — Base URL للحساب.
- `INFOBIP_API_KEY` — مفتاح Infobip.
- `INFOBIP_APPLICATION_ID` — معرف 2FA Application.
- `INFOBIP_MESSAGE_ID` — معرف SMS message template.
- `INFOBIP_SENDER` — Sender ID.
- `INFOBIP_TIMEOUT` — timeout للاتصال.

## الاختبارات

```bash
python3 tests/test_smoke.py
python3 tests/test_infobip.py
```

`test_infobip.py` يستخدم Infobip وهمي محلياً، لذلك لا يرسل SMS ولا يحتاج مفتاحاً حقيقياً، لكنه يفحص أن التطبيق يرسل payload الصحيح ويستخدم `pinId` للتحقق.

## قبل النشر العام

- استخدم HTTPS ودومين حقيقي.
- ضع المفاتيح في Environment Variables فقط، ولا تضع API Key داخل `server.py` أو `app.js`.
- غيّر `HASSA_ADMIN_KEY` الافتراضي.
- أضف rate limiting مركزي إذا شغلت أكثر من نسخة للخادم.
- انقل الصور إلى Object Storage عند زيادة الاستخدام.
- استخدم Push Notifications حقيقية ونسخ احتياطي للقاعدة.
- اختبر وصول SMS فعلياً على شبكات السودان قبل الإطلاق التجاري.

## ملاحظة أمنية

هذه نسخة MVP وليست Production-ready بالكامل. لا تستخدم بيانات حساسة على نطاق واسع قبل إكمال إدارة الأسرار، صلاحيات المستخدمين، rate limiting، النسخ الاحتياطي، المراقبة، وسياسة الخصوصية والاحتفاظ بالبيانات.
