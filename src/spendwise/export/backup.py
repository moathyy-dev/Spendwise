"""
Full local backup/restore of the sanitized database + app settings (never
includes .env / API keys / original uploaded files).
"""
from __future__ import annotations

import json
import os
import shutil
import zipfile
from datetime import datetime, timezone

BACKUP_FORMAT_VERSION = 1


def create_backup(output_path: str, db_path: str, settings_json_path: str) -> str:
    manifest = {
        "format_version": BACKUP_FORMAT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "app": "spendwise",
    }
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        if os.path.exists(db_path):
            zf.write(db_path, arcname="spendwise.db")
        if os.path.exists(settings_json_path):
            zf.write(settings_json_path, arcname="app_settings.json")
    return output_path


def restore_backup(backup_path: str, db_path: str, settings_json_path: str) -> None:
    with zipfile.ZipFile(backup_path, "r") as zf:
        names = zf.namelist()
        if "manifest.json" not in names:
            raise ValueError("ملف النسخة الاحتياطية غير صالح: لا يحتوي على manifest.json")
        manifest = json.loads(zf.read("manifest.json"))
        if manifest.get("format_version") != BACKUP_FORMAT_VERSION:
            raise ValueError("إصدار ملف النسخة الاحتياطية غير متوافق مع هذا الإصدار من البرنامج.")

        # Safety copy of the current DB before overwriting.
        if os.path.exists(db_path):
            shutil.copy2(db_path, db_path + ".pre_restore_backup.db")

        if "spendwise.db" in names:
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            with zf.open("spendwise.db") as src, open(db_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
        if "app_settings.json" in names:
            os.makedirs(os.path.dirname(settings_json_path), exist_ok=True)
            with zf.open("app_settings.json") as src, open(settings_json_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
