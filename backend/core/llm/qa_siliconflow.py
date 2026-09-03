import os
from typing import Optional

try:
    from openai import OpenAI

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


SILICONFLOW_API_KEY = os.environ.get("SILICONFLOW_API_KEY", "")
SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"

DEFAULT_MODEL = "Qwen/Qwen2.5-7B-Instruct"

_CLIENT = None

LANGUAGE_NAMES = {
    "zh": "Simplified Chinese",
    "en": "English",
    "ja": "Japanese",
    "fr": "French",
    "de": "German",
}


def get_client():
    global _CLIENT
    if _CLIENT is None and OPENAI_AVAILABLE:
        _CLIENT = OpenAI(
            api_key=SILICONFLOW_API_KEY,
            base_url=SILICONFLOW_BASE_URL,
        )
    return _CLIENT


class SiliconFlowQA:
    def __init__(self, model: str = DEFAULT_MODEL, api_key: str = None):
        self.model = model
        if api_key:
            self.client = OpenAI(api_key=api_key, base_url=SILICONFLOW_BASE_URL)
        else:
            self.client = get_client()

    def _build_messages(self, context: str, question: str, lang: str):
        answer_language = LANGUAGE_NAMES.get(lang, LANGUAGE_NAMES["zh"])

        system_prompt = (
            "You are a medical QA assistant. "
            f"Answer strictly in {answer_language}. "
            "Use only the evidence provided in the knowledge base context. "
            "Do not switch to another language unless the user explicitly asks you to translate. "
            "Keep the answer concise, medically cautious, and easy to read. "
            "Use 2 to 5 sentences. "
            "If the evidence is insufficient or irrelevant, say that the current knowledge base does not allow a reliable answer. "
            "Do not repeat characters, tokens, punctuation, or filler text."
        )

        if context:
            user_prompt = (
                "Knowledge base context:\n"
                f"{context}\n\n"
                "User question:\n"
                f"{question}\n\n"
                "Answer using only the context above."
            )
        else:
            user_prompt = question

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _build_translation_messages(self, text: str, src_lang: str, tgt_lang: str):
        src_name = LANGUAGE_NAMES.get(src_lang, src_lang or "source language")
        tgt_name = LANGUAGE_NAMES.get(tgt_lang, tgt_lang or "target language")
        system_prompt = (
            "You are a medical translation assistant. "
            f"Translate the input from {src_name} to {tgt_name}. "
            "Preserve the medical meaning exactly. "
            "Do not add explanations, disclaimers, bullets, or extra commentary. "
            "Return only the translated text."
        )
        user_prompt = (
            f"Source language: {src_name}\n"
            f"Target language: {tgt_name}\n\n"
            "Text:\n"
            f"{text}"
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def generate(
        self,
        prompt: str,
        context: str = "",
        question: str = "",
        lang: str = "zh",
        max_tokens: int = 500,
        temperature: float = 0.3,
    ) -> str:
        if not self.client:
            return "QA service is unavailable because the API client could not be initialized."

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self._build_messages(context=context, question=question, lang=lang),
                max_tokens=max_tokens,
                temperature=temperature,
                stream=False,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as e:
            return f"Failed to generate an answer: {e}"

    def translate(
        self,
        text: str,
        src_lang: str,
        tgt_lang: str,
        max_tokens: int = 500,
        temperature: float = 0.1,
    ) -> str:
        if not self.client:
            return "Translation service is unavailable because the API client could not be initialized."

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self._build_translation_messages(text=text, src_lang=src_lang, tgt_lang=tgt_lang),
                max_tokens=max_tokens,
                temperature=temperature,
                stream=False,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as e:
            return f"Failed to translate: {e}"

    def generate_stream(
        self,
        prompt: str,
        context: str = "",
        question: str = "",
        lang: str = "zh",
        max_tokens: int = 500,
        temperature: float = 0.3,
    ):
        if not self.client:
            yield "QA service is unavailable because the API client could not be initialized."
            return

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self._build_messages(context=context, question=question, lang=lang),
                max_tokens=max_tokens,
                temperature=temperature,
                stream=True,
            )

            for chunk in response:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content
        except Exception as e:
            yield f"Failed to generate an answer: {e}"


_qa_generator: Optional[SiliconFlowQA] = None


def get_qa_generator(model: str = DEFAULT_MODEL) -> SiliconFlowQA:
    global _qa_generator
    if _qa_generator is None or _qa_generator.model != model:
        _qa_generator = SiliconFlowQA(model=model)
    return _qa_generator


def reset_qa_generator():
    global _qa_generator
    _qa_generator = None
