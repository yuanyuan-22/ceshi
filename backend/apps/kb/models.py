from django.db import models
from django.conf import settings

class RawKBUpload(models.Model):
    class Meta:
        app_label = 'kb'
    FILE_TYPE_CHOICES = [
        ("txt", "TXT"),
        ("docx", "DOCX"),
        ("other", "Other"),
    ]
    STATUS_CHOICES = [
        ("NEW", "New"),
        ("PARSED", "Candidates Extracted"),
        ("REVIEWED", "Reviewed"),
        ("BUILD", "KB Built"),
    ]
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    file = models.FileField(upload_to="kb_uploads/%Y/%m/", null=True, blank=True)
    content = models.TextField(blank=True)
    file_type = models.CharField(max_length=20, choices=FILE_TYPE_CHOICES, default="txt")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="NEW")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        fname = getattr(self.file, 'name', '')
        return f"RawKBUpload({fname or 'text'}, by={self.uploaded_by})"


class CandidateEntity(models.Model):
    class Meta:
        app_label = 'kb'

    STATUS_CHOICES = [
        ("PENDING", "Pending Review"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
    ]

    raw_upload = models.ForeignKey(
        RawKBUpload,
        related_name='candidates',
        on_delete=models.CASCADE,
    )
    payload = models.JSONField(default=dict, blank=True)
    extraction_method = models.CharField(max_length=64, blank=True)
    confidence = models.FloatField(default=0.0)
    evidence_text = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    review_notes = models.TextField(blank=True)
    approved_entity = models.ForeignKey(
        'KBEntity',
        null=True,
        blank=True,
        related_name='candidate_sources',
        on_delete=models.SET_NULL,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name='reviewed_kb_candidates',
        on_delete=models.SET_NULL,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        payload = self.payload or {}
        langs = payload.get("langs") or {}
        zh = langs.get("zh") or {}
        en = langs.get("en") or {}
        label = zh.get("term") or en.get("term") or payload.get("canonical_key") or self.pk
        return f"CandidateEntity({label})"


class KBEntity(models.Model):
    class Meta:
        app_label = 'kb'
    entity_key = models.CharField(max_length=200, unique=True)
    canonical_key = models.CharField(max_length=200, blank=True)
    category = models.CharField(max_length=100, blank=True)
    source = models.CharField(max_length=100, blank=True)
    # per-language terms stored as a JSON blob for flexibility
    langs = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"KBEntity({self.entity_key or self.canonical_key})"


class TermCard(models.Model):
    class Meta:
        app_label = 'kb'
        verbose_name = 'Term Card'
        verbose_name_plural = 'Term Cards'
    entity = models.ForeignKey(KBEntity, related_name='term_cards', on_delete=models.CASCADE)
    lang = models.CharField(max_length=8)  # e.g. zh, en, ja, fr, de
    term = models.CharField(max_length=512, blank=True)
    type = models.CharField(max_length=64, blank=True)
    explain_text = models.TextField(blank=True)

    def __str__(self):
        return f"TermCard({self.lang}:{self.term})"
