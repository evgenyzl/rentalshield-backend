"""
Unit tests for the reconciler — uses mocked Claude responses.
No real API calls.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from rentalshield.compare.reconciler import DamageReconciler
from rentalshield.models import ComparisonStatus, DamageType


def _mock_message(json_payload: list[dict]) -> MagicMock:
    """Build a mock anthropic Message with a JSON body."""
    msg = MagicMock()
    msg.content = [MagicMock()]
    msg.content[0].text = json.dumps(json_payload)
    return msg


class TestDamageReconciler:
    @pytest.fixture
    def reconciler(self):
        with patch("rentalshield.compare.reconciler.anthropic.Anthropic"):
            r = DamageReconciler(api_key="sk-fake")
        return r

    def test_new_damage_detected(self, reconciler, sample_damages, sample_company_damages):
        """Damage in my list but not company list → NEW."""
        mock_response = [
            {"my_index": 0, "my_location": "front left door",
             "my_type": "SCRATCH", "my_description": "Thin scratch.",
             "status": "MATCHED", "reason": "LF door scratch documented by company."},
            {"my_index": 1, "my_location": "rear right fender",
             "my_type": "DENT", "my_description": "Small dent.",
             "status": "NEW", "reason": "Rear fender dent not in company report."},
            {"my_index": 2, "my_location": "front bumper center",
             "my_type": "CHIP", "my_description": "Paint chip.",
             "status": "MATCHED", "reason": "Front bumper chip documented."},
        ]

        reconciler._client.messages.create.return_value = _mock_message(mock_response)
        results = reconciler.compare(sample_damages, sample_company_damages)

        new_items = [r for r in results if r.status == ComparisonStatus.NEW]
        assert len(new_items) == 1
        assert new_items[0].my_location == "rear right fender"
        assert new_items[0].my_type     == DamageType.DENT

    def test_all_matched(self, reconciler, sample_damages, sample_company_damages):
        """All damages matched → no NEW items."""
        mock_response = [
            {"my_index": i, "my_location": d.location, "my_type": d.type.value,
             "my_description": d.description,
             "status": "MATCHED", "reason": "Documented."}
            for i, d in enumerate(sample_damages)
        ]
        reconciler._client.messages.create.return_value = _mock_message(mock_response)
        results = reconciler.compare(sample_damages, sample_company_damages)

        assert all(r.status == ComparisonStatus.MATCHED for r in results)

    def test_empty_my_damages(self, reconciler, sample_company_damages):
        """Empty damage list → empty comparison (no API call needed)."""
        results = reconciler.compare([], sample_company_damages)
        assert results == []
        reconciler._client.messages.create.assert_not_called()

    def test_malformed_response_raises(self, reconciler, sample_damages, sample_company_damages):
        """Truly malformed JSON from Claude propagates as JSONDecodeError."""
        reconciler._client.messages.create.return_value = _mock_message([])
        # Override to return bad JSON
        reconciler._client.messages.create.return_value.content[0].text = "NOT JSON"

        import json as _json
        with pytest.raises(_json.JSONDecodeError):
            reconciler.compare(sample_damages, sample_company_damages)
