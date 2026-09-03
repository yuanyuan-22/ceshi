from django.contrib import admin
from .models import TranslationTask


@admin.register(TranslationTask)
class TranslationTaskAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'src_lang', 'tgt_lang', 'base_translation', 'lora_translation', 'status', 'created_at']
    list_filter = ['status', 'src_lang', 'tgt_lang', 'domain', 'created_at']
    search_fields = ['input_text', 'base_translation', 'lora_translation']
    readonly_fields = ['created_at']
    ordering = ['-created_at']
    
    def base_translation(self, obj):
        return (obj.base_translation or "")[:50] + ("..." if len(obj.base_translation or "") > 50 else "")
    base_translation.short_description = 'Base翻译'
    
    def lora_translation(self, obj):
        return (obj.lora_translation or "")[:50] + ("..." if len(obj.lora_translation or "") > 50 else "")
    lora_translation.short_description = 'LoRA翻译'
