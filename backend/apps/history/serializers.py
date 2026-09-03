# backend/apps/history/serializers.py
from rest_framework import serializers


class TranslationHistoryItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    created_at = serializers.DateTimeField(required=False)
    input_text = serializers.CharField(allow_blank=True, required=False)
    output_text = serializers.CharField(allow_blank=True, required=False)
    src_lang = serializers.CharField(allow_blank=True, required=False)
    tgt_lang = serializers.CharField(allow_blank=True, required=False)
    domain = serializers.CharField(allow_blank=True, required=False)
    terms_json = serializers.JSONField(required=False)


class QAHistoryItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    created_at = serializers.DateTimeField(required=False)
    question = serializers.CharField(allow_blank=True, required=False)
    answer = serializers.CharField(allow_blank=True, required=False)
    sources = serializers.JSONField(required=False)   # 你 qa.html 用的 sources/citations 都可以塞这里
    extra = serializers.JSONField(required=False)     # 预留（latency、top_k、raw_response 等）