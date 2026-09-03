from django.contrib import admin

from .models import CandidateEntity, RawKBUpload, KBEntity, TermCard


@admin.register(RawKBUpload)
class RawKBUploadAdmin(admin.ModelAdmin):
    list_display = ("id", "uploaded_by", "file_type", "status", "created_at")
    search_fields = ("file__name", "content")


@admin.register(KBEntity)
class KBEntityAdmin(admin.ModelAdmin):
    list_display = ("entity_key", "canonical_key", "category")
    search_fields = ("entity_key", "canonical_key", "category")


@admin.register(CandidateEntity)
class CandidateEntityAdmin(admin.ModelAdmin):
    list_display = ("id", "raw_upload", "status", "confidence", "extraction_method", "approved_entity", "reviewed_by")
    list_filter = ("status", "extraction_method")
    search_fields = ("payload", "review_notes", "evidence_text")


@admin.register(TermCard)
class TermCardAdmin(admin.ModelAdmin):
    list_display = ("entity", "lang", "term", "type")
    search_fields = ("term", "explain_text", "lang")
