from django.conf import settings
from django.db import models

class TranslationTask(models.Model):
    STATUS_CHOICES = [
        ("SUCCESS", "SUCCESS"),
        ("FAIL", "FAIL"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="translation_tasks")
    src_lang = models.CharField(max_length=16, default="en")
    tgt_lang = models.CharField(max_length=16, default="zh")
    domain = models.CharField(max_length=32, default="general")

    input_text = models.TextField()
    
    base_translation = models.TextField('Base模型翻译', blank=True, default="")
    lora_translation = models.TextField('LoRA模型翻译', blank=True, default="")
    output_text = models.TextField('最终翻译(同LoRA)', blank=True, default="")
    
    terms_json = models.JSONField(blank=True, default=list)

    latency_ms = models.IntegerField(default=0)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="SUCCESS")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]