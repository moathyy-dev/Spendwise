#!/usr/bin/env bash
# إعداد SpendWise لأول مرة على macOS أو Linux.
set -e

cd "$(dirname "$0")/.."

echo "=== إنشاء بيئة بايثون افتراضية (venv) ==="
python3 -m venv .venv

echo "=== تفعيل البيئة الافتراضية وتثبيت المتطلبات ==="
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install -e .

if [ ! -f .env ]; then
  echo "=== إنشاء ملف .env من .env.example ==="
  cp .env.example .env
  echo "تم إنشاء ملف .env — يمكنك تعديله لاحقًا لإضافة مفتاح Gemini إن رغبت."
fi

echo "=== تطبيق ترحيلات قاعدة البيانات ==="
alembic upgrade head

echo ""
echo "✅ تم الإعداد بنجاح! لتشغيل التطبيق استخدم: bash scripts/run_unix.sh"
