from spendwise.ai_provider import build_ai_provider
from spendwise.ai_provider.gemini_provider import GeminiProvider
from spendwise.ai_provider.null_provider import NullAIProvider


def test_build_ai_provider_returns_null_when_disabled(settings_factory):
    settings = settings_factory(enable_online_ai=False)
    provider = build_ai_provider(settings)
    assert isinstance(provider, NullAIProvider)


def test_build_ai_provider_returns_null_when_gemini_unconfigured(settings_factory):
    settings = settings_factory(enable_online_ai=True, ai_provider="gemini", gemini_api_key="")
    provider = build_ai_provider(settings)
    assert isinstance(provider, NullAIProvider)


def test_null_provider_never_fails_and_returns_empty():
    provider = NullAIProvider()
    assert provider.is_configured() is True
    assert provider.classify_batch([], []) == []


def test_gemini_parse_response_filters_unknown_rows_and_categories():
    categories = [{"id": 1, "name": "طعام"}]
    raw = '[{"row_index": 0, "category_id": 1, "confidence": 90, "explanation_ar": "test"}, {"row_index": 99, "category_id": 1, "confidence": 90, "explanation_ar": "ignored"}]'
    results = GeminiProvider._parse_response(raw, valid_row_indices={0}, categories=categories)
    assert len(results) == 1
    assert results[0].row_index == 0
    assert results[0].category_id == 1


def test_gemini_parse_response_downgrades_unknown_category():
    categories = [{"id": 1, "name": "طعام"}]
    raw = '[{"row_index": 0, "category_id": 999, "confidence": 90, "explanation_ar": "test"}]'
    results = GeminiProvider._parse_response(raw, valid_row_indices={0}, categories=categories)
    assert results[0].category_id is None
    assert results[0].confidence <= 40


def test_gemini_parse_response_handles_malformed_json():
    results = GeminiProvider._parse_response("not json at all", valid_row_indices={0}, categories=[])
    assert results == []


def test_gemini_parse_response_handles_non_list_json():
    results = GeminiProvider._parse_response('{"unexpected": "object"}', valid_row_indices={0}, categories=[])
    assert results == []


def test_gemini_parse_response_clamps_confidence():
    categories = [{"id": 1, "name": "طعام"}]
    raw = '[{"row_index": 0, "category_id": 1, "confidence": 500, "explanation_ar": "test"}]'
    results = GeminiProvider._parse_response(raw, valid_row_indices={0}, categories=categories)
    assert results[0].confidence == 100
