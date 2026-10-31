# نشر هسّع — نسخة تجريبية

هذه النسخة تعمل كخدمة Python واحدة وتخدم الواجهة والـAPI معاً. أسهل نشر تجريبي هو أي منصة تدعم Docker أو تشغيل `python3 server.py`.

## متغيرات البيئة الأساسية

- `HASSA_DEV_OTP=0` للإنتاج
- `HASSA_ADMIN_KEY` مفتاح إدارة قوي وعشوائي
- `HASSA_DB` مسار قاعدة SQLite على قرص دائم إن كانت المنصة تدعم Persistent Disk
- إعدادات Infobip المذكورة في README

## تنبيه SQLite

في الاستضافة التجريبية التي لا توفر قرصاً دائماً قد تُمسح قاعدة البيانات عند إعادة تشغيل الحاوية. للإطلاق التجاري انقل البيانات إلى قاعدة مُدارة مثل PostgreSQL أو استخدم قرصاً دائماً.

## Docker محلياً

```bash
docker build -t hassa-app .
docker run --rm -p 8080:8080 -e HASSA_DEV_OTP=1 hassa-app
```

ثم افتح `http://localhost:8080`.

## Railway

راجع `RAILWAY.md`. عند تركيب Railway Volume، يلتقط التطبيق `RAILWAY_VOLUME_MOUNT_PATH` تلقائياً ويضع قاعدة البيانات داخله.
