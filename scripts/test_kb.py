#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""KB 术语库功能自测：普通用户上传/浏览、管理员处理、模板渲染。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import django

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "backend" / "apps"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings  # noqa: E402
if "testserver" not in settings.ALLOWED_HOSTS and "*" not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]

from django.contrib.auth.models import User  # noqa: E402
from django.template.loader import render_to_string  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402


def main():
    print("===== [1] 模板渲染检查 =====")
    for tpl in ("kb_user_dashboard.html", "kb_dashboard_redirect.html"):
        try:
            render_to_string(tpl, {"active": "kb"})
            print(f"  OK  {tpl}")
        except Exception as e:
            print(f"  FAIL {tpl}: {e}")

    print("\n===== [2] 普通用户上传文本 =====")
    user, _ = User.objects.get_or_create(username="kb_test_user", defaults={"is_staff": False})
    client = APIClient()
    client.force_authenticate(user=user)

    r = client.post("/api/kb/upload/", {"text": "糖尿病是一种以高血糖为特征的代谢性疾病。"}, format="json")
    print(f"  upload text -> {r.status_code} {r.json() if r.status_code < 500 else r.content[:200]}")
    upload_id = r.json().get("upload_id") if r.status_code == 200 else None

    print("\n===== [3] 普通用户浏览 =====")
    for path in ("/api/kb/entities/", "/api/kb/summary/", "/api/kb/upload_list/"):
        r = client.get(path)
        body = r.json()
        n = len(body) if isinstance(body, list) else body
        print(f"  GET {path} -> {r.status_code} {n}")

    print("\n===== [4] 普通用户不能触发处理（应 403）=====")
    if upload_id:
        r = client.post(f"/api/kb/process/{upload_id}/", {}, format="json")
        print(f"  process (user) -> {r.status_code} (期望 403)")

    print("\n===== [5] 管理员处理该上传 =====")
    admin, _ = User.objects.get_or_create(username="kb_test_admin", defaults={"is_staff": True})
    if not admin.is_staff:
        admin.is_staff = True
        admin.save()
    admin_client = APIClient()
    admin_client.force_authenticate(user=admin)
    if upload_id:
        r = admin_client.post(f"/api/kb/process/{upload_id}/", {"category": "disease"}, format="json")
        print(f"  process (admin) -> {r.status_code} candidates={r.json().get('candidate_count') if r.status_code==200 else r.content[:200]}")

    print("\n===== 清理测试数据 =====")
    from backend.apps.kb.models import RawKBUpload
    RawKBUpload.objects.filter(uploaded_by__in=[user]).delete()
    User.objects.filter(username__in=["kb_test_user", "kb_test_admin"]).delete()
    print("  done")


if __name__ == "__main__":
    main()
