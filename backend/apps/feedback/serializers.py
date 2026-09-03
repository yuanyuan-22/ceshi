from rest_framework import serializers
from .models import Feedback


class FeedbackCreateSerializer(serializers.ModelSerializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    original_translation = serializers.CharField(required=False, allow_blank=True, default="")
    input_text = serializers.CharField(required=False, allow_blank=True, default="")
    src_lang = serializers.CharField(required=False, allow_blank=True, default="")
    tgt_lang = serializers.CharField(required=False, allow_blank=True, default="")
    score = serializers.IntegerField(required=False, min_value=0, max_value=10)
    related_entities = serializers.ListField(required=False, child=serializers.CharField(), default=list)
    question = serializers.CharField(required=False, allow_blank=True, default="")
    ai_answer = serializers.CharField(required=False, allow_blank=True, default="")

    class Meta:
        model = Feedback
        fields = [
            "scene", "task_type", "task_id",
            "rating", "score",
            "rating_accuracy", "rating_clarity", "rating_completeness", "rating_safety",
            "comment", "corrected_translation", "corrected_answer",
            "related_entities", "extra",
            "reason", "original_translation", "input_text", "src_lang", "tgt_lang",
            "question", "ai_answer",
        ]

    def validate_scene(self, v):
        if v not in dict(Feedback.Scene.choices):
            raise serializers.ValidationError("Invalid scene")
        return v

    def validate_rating(self, v):
        if v not in (-1, 0, 1) and not (1 <= v <= 10):
            raise serializers.ValidationError("rating must be -1, 0, 1, or 1..10")
        return v

    def validate_score(self, v):
        if v is None:
            return v
        if not (0 <= v <= 10):
            raise serializers.ValidationError("score must be between 0 and 10")
        return v

    def create(self, validated_data):
        reason = validated_data.pop("reason", "") or ""
        original_translation = validated_data.pop("original_translation", "") or ""
        input_text = validated_data.pop("input_text", "") or ""
        src_lang = validated_data.pop("src_lang", "") or ""
        tgt_lang = validated_data.pop("tgt_lang", "") or ""
        score = validated_data.pop("score", None)
        related_entities = validated_data.pop("related_entities", [])
        question = validated_data.pop("question", "") or ""
        ai_answer = validated_data.pop("ai_answer", "") or ""

        extra = validated_data.get("extra") or {}
        if reason:
            extra["reason"] = reason
        if original_translation:
            extra["original_translation"] = original_translation
        if input_text:
            extra["input_text"] = input_text
        if src_lang:
            extra["src_lang"] = src_lang
        if tgt_lang:
            extra["tgt_lang"] = tgt_lang
        if score is not None:
            extra["score"] = score

        validated_data["extra"] = extra

        if related_entities:
            validated_data["related_entity_keys"] = [
                e.strip() for e in related_entities if e.strip()
            ]

        if not validated_data.get("corrected_answer") and (question or ai_answer):
            extra["question"] = question
            extra["ai_answer"] = ai_answer

        return super().create(validated_data)

    def validate(self, attrs):
        scene = attrs.get("scene")
        rating = attrs.get("rating")
        if scene == Feedback.Scene.SYSTEM:
            if rating is None or not (0 <= rating <= 10):
                raise serializers.ValidationError({"rating": "system feedback rating must be between 0 and 10"})
        return attrs


class FeedbackListSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = Feedback
        fields = [
            "id", "created_at", "scene", "task_type", "task_id",
            "rating", "rating_accuracy", "rating_clarity", "rating_completeness", "rating_safety",
            "extra", "comment", "corrected_translation", "corrected_answer",
            "related_entity_keys", "resolution", "resolved_at", "resolution_note",
            "user_id", "username",
        ]


class FeedbackResolveSerializer(serializers.Serializer):
    resolution = serializers.ChoiceField(choices=Feedback.Resolution.choices)
    note = serializers.CharField(required=False, allow_blank=True, default="")
