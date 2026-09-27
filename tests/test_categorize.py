from dataclasses import dataclass

from spendwise.ai_provider.base import AIClassificationOutput, AIProviderError
from spendwise.categorize.default_rules import seed_default_rules
from spendwise.categorize.rules_engine import classify_with_rules, normalize_merchant_for_matching
from spendwise.categorize.service import classify_batch, create_learned_rule
from spendwise.db.models import Category, Rule, RuleType


@dataclass
class _FakeRow:
    row_index: int
    merchant_sanitized: str
    amount: str = "50.00"
    direction: str = "debit"


class FakeAIProvider:
    def __init__(self, outputs=None, raise_error=False):
        self._outputs = outputs or []
        self._raise_error = raise_error

    def is_configured(self):
        return True

    def classify_batch(self, transactions, categories):
        if self._raise_error:
            raise AIProviderError("simulated failure")
        return self._outputs


def test_normalize_merchant_for_matching_strips_diacritics_and_case():
    assert normalize_merchant_for_matching("STARBUCKS") == normalize_merchant_for_matching("starbucks")
    assert normalize_merchant_for_matching("  ستاربكس  ") == "ستاربكس"


def test_classify_with_rules_exact_match(db_session):
    category = db_session.query(Category).filter(Category.parent_id.isnot(None)).first()
    rule = Rule(rule_type=RuleType.EXACT, pattern="ستاربكس", category_id=category.id, priority=10, is_active=True)
    db_session.add(rule)
    db_session.commit()

    result = classify_with_rules("ستاربكس", [rule])
    assert result.source == "rule"
    assert result.category_id == category.id
    assert result.confidence == 100


def test_classify_with_rules_no_match_returns_unclassified(db_session):
    result = classify_with_rules("متجر غير معروف تمامًا", [])
    assert result.source == "unclassified"
    assert result.category_id is None


def test_priority_order_wins_over_type(db_session):
    category = db_session.query(Category).filter(Category.parent_id.isnot(None)).first()
    other_category = db_session.query(Category).filter(Category.parent_id.isnot(None), Category.id != category.id).first()

    exact_rule = Rule(rule_type=RuleType.EXACT, pattern="مطعم", category_id=category.id, priority=50, is_active=True)
    keyword_rule = Rule(rule_type=RuleType.KEYWORD, pattern="مطعم", category_id=other_category.id, priority=1, is_active=True)
    db_session.add_all([exact_rule, keyword_rule])
    db_session.commit()

    result = classify_with_rules("مطعم", [exact_rule, keyword_rule])
    # keyword_rule has lower (higher-priority) priority number, so it should win despite EXACT normally winning ties.
    assert result.category_id == other_category.id


def test_seed_default_rules_creates_global_keyword_rules(db_session):
    seed_default_rules(db_session)
    db_session.commit()
    rules = db_session.query(Rule).filter(Rule.family_member_id.is_(None), Rule.rule_type == RuleType.KEYWORD).all()
    assert len(rules) > 0


def test_classify_batch_auto_approves_high_confidence(db_session, settings_factory):
    seed_default_rules(db_session)
    db_session.commit()
    settings = settings_factory(confidence_auto_accept=50)  # keyword rules give 75 confidence

    rows = [_FakeRow(row_index=0, merchant_sanitized="ستاربكس")]
    results = classify_batch(db_session, family_member_id=1, rows=rows, settings=settings, ai_provider=None)
    assert len(results) == 1
    assert results[0].category_id is not None
    assert results[0].needs_review is False


def test_classify_batch_falls_back_to_ai_when_below_threshold(db_session, settings_factory):
    settings = settings_factory(enable_online_ai=True, confidence_ai_fallback=80)
    category = db_session.query(Category).filter(Category.parent_id.isnot(None)).first()

    fake_ai = FakeAIProvider(outputs=[AIClassificationOutput(row_index=0, category_id=category.id, confidence=90, explanation_ar="ai")])
    rows = [_FakeRow(row_index=0, merchant_sanitized="متجر غير معروف تمامًا")]
    results = classify_batch(db_session, family_member_id=1, rows=rows, settings=settings, ai_provider=fake_ai)
    assert results[0].source == "ai"
    assert results[0].category_id == category.id
    assert results[0].needs_review is True


def test_classify_batch_ai_failure_does_not_break_batch(db_session, settings_factory):
    settings = settings_factory(enable_online_ai=True)
    fake_ai = FakeAIProvider(raise_error=True)
    rows = [_FakeRow(row_index=0, merchant_sanitized="متجر غير معروف تمامًا")]
    results = classify_batch(db_session, family_member_id=1, rows=rows, settings=settings, ai_provider=fake_ai)
    assert len(results) == 1  # did not raise, local-rules result preserved
    assert results[0].source == "unclassified"


def test_create_learned_rule_only_when_future_scope(db_session):
    category = db_session.query(Category).filter(Category.parent_id.isnot(None)).first()
    rule = create_learned_rule(db_session, family_member_id=1, merchant_sanitized="متجري", category_id=category.id, scope="single")
    assert rule is None

    rule2 = create_learned_rule(db_session, family_member_id=1, merchant_sanitized="متجري", category_id=category.id, scope="future_rule")
    assert rule2 is not None
    assert rule2.rule_type == RuleType.LEARNED
