#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""管理台功能点自测：完整走一遍管理员在 kb_dashboard.js 里会触发的所有接口。"""
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
from rest_framework.test import APIClient  # noqa: E402


def check(label, cond, extra=""):
    print(f"  {'OK ' if cond else 'FAIL'} {label} {extra}")
    return cond


def main():
    admin, _ = User.objects.get_or_create(username="kb_admin_probe", defaults={"is_staff": True})
    if not admin.is_staff:
        admin.is_staff = True
        admin.save()
    c = APIClient()
    c.force_authenticate(user=admin)

    print("===== 上传 -> 抽取候选 =====")
    r = c.post("/api/kb/upload/", {"text": "急性心肌梗死是冠状动脉急性闭塞导致的心肌缺血坏死。高血压是常见慢性病。"}, format="json")
    upload_id = r.json().get("upload_id")
    check("POST /api/kb/upload/", r.status_code == 200, f"upload_id={upload_id}")

    r = c.post(f"/api/kb/process/{upload_id}/", {}, format="json")
    cand_n = r.json().get("candidate_count") if r.status_code == 200 else None
    check("POST /api/kb/process/<id>/ (抽取候选实体)", r.status_code == 200, f"candidates={cand_n}")

    print("===== viewUploadDetail: GET /api/kb/uploads/<id>/ =====")
    r = c.get(f"/api/kb/uploads/{upload_id}/")
    body = r.json() if r.status_code == 200 else {}
    check("GET /api/kb/uploads/<id>/", r.status_code == 200,
          f"related_candidates={len(body.get('related_candidates', []))}")

    print("===== loadCandidateList: GET /api/kb/candidates/?upload_id=<id> =====")
    r = c.get(f"/api/kb/candidates/?upload_id={upload_id}")
    cands = r.json() if r.status_code == 200 else []
    check("GET /api/kb/candidates/?upload_id=", r.status_code == 200, f"n={len(cands)}")

    cand_id = cands[0]["id"] if cands else None
    print("===== selectCandidate: GET /api/kb/candidates/<id>/ =====")
    if cand_id:
        r = c.get(f"/api/kb/candidates/{cand_id}/")
        check("GET /api/kb/candidates/<id>/", r.status_code == 200,
              f"label={r.json().get('label') if r.status_code == 200 else r.content[:120]}")

        print("===== approveCurrentCandidate: PATCH + approve =====")
        r = c.patch(f"/api/kb/candidates/{cand_id}/", {"review_notes": "probe"}, format="json")
        check("PATCH /api/kb/candidates/<id>/", r.status_code == 200)
        r = c.post(f"/api/kb/candidates/{cand_id}/approve/", {"review_notes": "probe ok"}, format="json")
        entity_id = r.json().get("entity_id") if r.status_code == 200 else None
        check("POST /api/kb/candidates/<id>/approve/", r.status_code == 200, f"entity_id={entity_id}")
    else:
        entity_id = None

    print("===== loadEntities / selectEntity =====")
    r = c.get("/api/kb/entities/")
    ents = r.json() if r.status_code == 200 else []
    check("GET /api/kb/entities/", r.status_code == 200, f"n={len(ents)}")
    detail_id = entity_id or (ents[0]["id"] if ents else None)
    if detail_id:
        r = c.get(f"/api/kb/entities/{detail_id}/")
        ok = r.status_code == 200
        check("GET /api/kb/entities/<id>/", ok,
              f"term_cards={len(r.json().get('term_cards', [])) if ok else r.content[:120]}")

    print("===== 汇总 =====")
    r = c.get("/api/kb/summary/")
    check("GET /api/kb/summary/", r.status_code == 200, str(r.json() if r.status_code == 200 else ""))

    print("===== 清理 =====")
    from backend.apps.kb.models import RawKBUpload
    RawKBUpload.objects.filter(uploaded_by=admin).delete()
    if detail_id:
        from backend.apps.kb.models import KBEntity
        KBEntity.objects.filter(id=detail_id).delete()
    User.objects.filter(username="kb_admin_probe").delete()
    print("  done")


if __name__ == "__main__":
    main()
