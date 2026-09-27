"""
Gemini implementation of the AIProvider interface (free tier by default).

Only sanitized fields (merchant label, amount, debit/credit direction) are
ever sent — never raw descriptions, account numbers, or personal data.
Responses are strictly parsed as JSON against an expected schema; anything
malformed is dropped rather than trusted. Retries with backoff on transient
failures; raises AIProviderError only if the whole batch ultimately fails,
so the caller can fall back to local-rules-only results.
"""
from __future__ import annotations

import json
import time

from spendwise.ai_provider.base import (
    AIClassificationOutput,
    AIProvider,
    AIProviderError,
    AITransactionInput,
)

_MAX_BATCH_SIZE = 25


class GeminiProvider(AIProvider):
    def __init__(self, api_key: str, model_name: str = "gemini-1.5-flash", timeout_seconds: int = 20, max_retries: int = 2):
        self._api_key = api_key
        self._model_name = model_name
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._model = None

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        import google.generativeai as genai

        genai.configure(api_key=self._api_key)
        self._model = genai.GenerativeModel(self._model_name)
        return self._model

    def classify_batch(
        self, transactions: list[AITransactionInput], categories: list[dict]
    ) -> list[AIClassificationOutput]:
        if not self.is_configured():
            raise AIProviderError("مزوّد Gemini غير مُهيَّأ (لا يوجد مفتاح API).")

        results: list[AIClassificationOutput] = []
        for i in range(0, len(transactions), _MAX_BATCH_SIZE):
            chunk = transactions[i : i + _MAX_BATCH_SIZE]
            results.extend(self._classify_chunk(chunk, categories))
        return results

    def _classify_chunk(
        self, chunk: list[AITransactionInput], categories: list[dict]
    ) -> list[AIClassificationOutput]:
        model = self._ensure_model()
        prompt = self._build_prompt(chunk, categories)
        valid_row_indices = {t.row_index for t in chunk}

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = model.generate_content(
                    prompt,
                    generation_config={"response_mime_type": "application/json", "temperature": 0},
                    request_options={"timeout": self._timeout_seconds},
                )
                return self._parse_response(response.text, valid_row_indices, categories)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt < self._max_retries:
                    time.sleep(min(2**attempt, 8))
                    continue
        raise AIProviderError(f"فشل الاتصال بمزوّد الذكاء الاصطناعي بعد عدة محاولات: {last_error}")

    @staticmethod
    def _build_prompt(chunk: list[AITransactionInput], categories: list[dict]) -> str:
        categories_json = json.dumps(categories, ensure_ascii=False)
        txns_json = json.dumps(
            [
                {"row_index": t.row_index, "merchant": t.merchant_sanitized, "amount": t.amount, "direction": t.direction}
                for t in chunk
            ],
            ensure_ascii=False,
        )
        return (
            "أنت مساعد لتصنيف معاملات مالية شخصية. لديك قائمة تصنيفات متاحة، وقائمة معاملات "
            "(اسم تاجر مُنقّى من أي معلومات حساسة، والمبلغ، والاتجاه مدين/دائن فقط).\n"
            "التصنيفات المتاحة (JSON):\n" + categories_json + "\n\n"
            "المعاملات (JSON):\n" + txns_json + "\n\n"
            "أعد فقط مصفوفة JSON (بدون أي نص إضافي) بهذا الشكل تمامًا:\n"
            '[{"row_index": <int>, "category_id": <int أو null>, "confidence": <0-100>, '
            '"explanation_ar": "<جملة قصيرة بالعربية>"}]\n'
            "استخدم category_id=null إذا لم تكن متأكدًا. لا تُخرج أي شيء خارج هذه المصفوفة."
        )

    @staticmethod
    def _parse_response(raw_text: str, valid_row_indices: set[int], categories: list[dict]) -> list[AIClassificationOutput]:
        valid_category_ids = {c["id"] for c in categories}
        try:
            data = json.loads(raw_text)
        except (json.JSONDecodeError, TypeError):
            return []
        if not isinstance(data, list):
            return []

        outputs: list[AIClassificationOutput] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            row_index = item.get("row_index")
            if row_index not in valid_row_indices:
                continue
            category_id = item.get("category_id")
            confidence = item.get("confidence", 0)
            try:
                confidence = int(confidence)
            except (TypeError, ValueError):
                confidence = 0
            confidence = max(0, min(100, confidence))

            if category_id is not None and category_id not in valid_category_ids:
                category_id = None
                confidence = min(confidence, 40)

            explanation = item.get("explanation_ar") or "تم التصنيف بواسطة الذكاء الاصطناعي."
            outputs.append(
                AIClassificationOutput(
                    row_index=row_index, category_id=category_id, confidence=confidence, explanation_ar=str(explanation)
                )
            )
        return outputs
