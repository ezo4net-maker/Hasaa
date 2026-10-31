# نشر هسّع على Render

## أسرع نسخة تجريبية مجانية
استخدم `render.yaml`.

- Runtime: Docker
- Plan: Free
- Health check: `/api/health`
- OTP: وضع تطوير (`HASSA_DEV_OTP=1`)
- مفتاح الإدارة: يولده Render تلقائياً.

> ملاحظة مهمة: خدمة Render المجانية تستخدم نظام ملفات مؤقتاً. قاعدة SQLite المحلية قد تُمسح عند إعادة التشغيل أو الـredeploy أو بعد spin-down.

## نسخة ببيانات دائمة
استخدم `render-paid.yaml` أو أضف Persistent Disk على `/var/data` واضبط:

`HASSA_DB=/var/data/hassa.db`

## تشغيل Infobip الحقيقي لاحقاً
اضبط هذه القيم كـSecrets في Render ثم غيّر `HASSA_DEV_OTP=0`:

- `INFOBIP_API_KEY`
- `INFOBIP_BASE_URL`
- `INFOBIP_APPLICATION_ID`
- `INFOBIP_MESSAGE_ID`
- `INFOBIP_SENDER`

لا تضع مفاتيح API داخل Git أو داخل الملفات العامة.
