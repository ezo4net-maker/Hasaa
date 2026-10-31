# نشر هسّع على Railway

هذه الحزمة جاهزة للنشر كخدمة Docker على Railway.

## الإعداد الموصى به

1. أنشئ Service من هذا المشروع/المستودع. Railway سيكتشف `Dockerfile` تلقائياً.
2. أضف Volume واربطه بالخدمة. التطبيق سيستخدم `RAILWAY_VOLUME_MOUNT_PATH/hassa.db` تلقائياً.
3. أضف متغيرات البيئة:
   - `HASSA_DEV_OTP=0`
   - `HASSA_ADMIN_KEY=<قيمة عشوائية قوية>`
   - `INFOBIP_API_KEY=<secret>`
   - `INFOBIP_BASE_URL=<your-infobip-base-url>`
   - `INFOBIP_APPLICATION_ID=<2fa-app-id>`
   - `INFOBIP_MESSAGE_ID=<2fa-template-id>`
   - `INFOBIP_SENDER=<approved-sender>`
4. وللاختبار قبل Infobip، استخدم `HASSA_DEV_OTP=1` مؤقتاً فقط.
5. افحص `/api/health` بعد النشر؛ يجب أن يرجع `ok: true`.

> لا تضع مفاتيح Infobip داخل الملفات أو Git. استخدم Variables/Secrets في Railway.
