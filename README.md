[README.md](https://github.com/user-attachments/files/27588820/README.md)
# Shareex Analytics Dashboard 🚀

داشبورد تحليل الشحنات — مبني بـ Python Dash + Plotly

---

## تشغيل محلياً

```bash
pip install -r requirements.txt
python shareex_dashboard.py
```
ثم افتح المتصفح: http://localhost:8050

---

## نشر أونلاين (مجاناً)

### الطريقة 1 — Render.com (الأسهل)

1. ارفع الملفين على GitHub (repo جديد)
2. اذهب إلى https://render.com → New Web Service
3. اربطه بالـ repo
4. أهم الإعدادات:
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `gunicorn shareex_dashboard:server`
   - **Plan:** Free

---

### الطريقة 2 — Railway.app

1. ارفع على GitHub
2. https://railway.app → New Project → Deploy from GitHub
3. يشتغل تلقائياً (يقرأ requirements.txt)

---

### الطريقة 3 — PythonAnywhere

1. سجّل مجاناً على https://pythonanywhere.com
2. Web tab → Add new web app → Flask
3. ارفع الملف وعدّل WSGI ليشير إلى `server`

---

## ملف Excel المطلوب

الأعمدة المدعومة (أي منها):

| الاسم الإنجليزي | الاسم العربي |
|---|---|
| Ref / Invoice | رقم الشحنة |
| Pickup / PickupDate | تاريخ الاستلام |
| Name / Customer | الاسم |
| Area / Region | المنطقة |
| Account / Client | الحساب |
| finalstatusname / Status | الحالة |
| Courier / Driver | المندوب |
| Phone / Mobile / Tel | الهاتف |
| Notes | ملاحظات |

**الحالات المعتمدة:**
- `OK` → يُحوَّل إلى **تم التسليم**
- `Branch Delivered` → يُحوَّل إلى **في الفرع**

---

## الصفحات

| الصفحة | المحتوى |
|---|---|
| نظرة عامة | 5 KPIs + اتجاه يومي + Pie + أفضل مناديب |
| الشحنات | جدول كامل مع فلترة وبحث وتصدير |
| المناديب | تصنيف + charts أداء + جدول تفصيلي |
| التقادم | تحليل الشحنات المتأخرة حسب الأيام |
