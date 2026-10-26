"""Unit tests for evidence combination, conflict detection and citation formatting."""

from apps.backend import answer
from rag.retrieval.retriever import format_citation

SOP = {
    "ref": "D1",
    "doc_id": "SOP-BFP-001",
    "title": "Boiler Feed Pump Operating Procedure",
    "section": "High Discharge Pressure Alarm Response",
    "doc_type": "operating_procedure",
    "text": "1. Check the position of the feedwater control valve FCV-101 on the DCS.\n"
    "2. Confirm the reading on the local pressure gauge to rule out a faulty pressure transmitter.\n"
    "Restart rule: Do not reset the trip or restart the pump until the cause has been identified.",
}
GUIDE = {
    "ref": "D2",
    "doc_id": "TG-VLV-006",
    "title": "Control Valve Troubleshooting Guide",
    "section": "Valve Position Deviation",
    "doc_type": "troubleshooting_guide",
    "text": "Likely causes: low instrument air pressure, positioner out of calibration.",
}


def action(text):
    return {"step": 1, "action": text, "urgency": "immediate", "source": "alarm_api_rule_engine"}


def test_conflicting_recommendation_is_detected():
    result = answer.compare_with_documents(
        [action("If pressure stays high, reset the trip and restart the pump to clear the alarm")], [SOP]
    )
    assert result[0]["doc_check"] == "conflict"
    assert result[0]["doc_ref"] == "D1"
    assert "Do not reset" in result[0]["doc_sentence"]


def test_supported_recommendation():
    result = answer.compare_with_documents(
        [action("Verify discharge pressure on the local gauge to rule out a faulty transmitter")], [SOP]
    )
    assert result[0]["doc_check"] == "supported"


def test_precaution_is_not_a_conflict():
    doc = dict(SOP, text="Do not attempt a restart before the cause is known.")
    result = answer.compare_with_documents([action("Measure insulation resistance before any restart attempt")], [doc])
    assert result[0]["doc_check"] != "conflict"


def test_action_not_in_documents():
    result = answer.compare_with_documents([action("Call the vendor hotline for a firmware update")], [SOP])
    assert result[0]["doc_check"] == "not_covered"
    assert result[0]["doc_ref"] is None


def test_document_causes_only_from_cause_sections():
    causes = answer.document_causes([SOP, GUIDE], focus_words=set())
    assert causes and all(c["ref"] == "D2" for c in causes)


def test_likely_causes_from_correlation():
    correlation = {
        "correlated_pairs": [
            {
                "leading_alarm": {
                    "asset_id": "AST-FCV-101",
                    "asset_name": "FCV-101",
                    "alarm_name": "Valve Position Deviation",
                },
                "following_alarm": {
                    "asset_id": "AST-BFP-101",
                    "asset_name": "BFP 101",
                    "alarm_name": "High Discharge Pressure",
                },
                "support": 30,
                "confidence": 0.75,
                "avg_lag_minutes": 3.0,
            }
        ]
    }
    causes = answer.likely_causes_from_correlation(correlation, {"AST-BFP-101"}, "High Discharge Pressure", "T6")
    assert len(causes) == 1
    assert causes[0]["ref"] == "T6"
    assert "precedes" in causes[0]["cause"]


def test_citation_format_and_numbering():
    numbered = answer.number_documents([SOP, GUIDE])
    assert [d["ref"] for d in numbered] == ["D1", "D2"]
    assert (
        format_citation(SOP)
        == 'SOP-BFP-001 - Boiler Feed Pump Operating Procedure, section "High Discharge Pressure Alarm Response"'
    )


def test_pick_procedure_prefers_operating_procedure():
    assert answer.pick_procedure(answer.number_documents([GUIDE, SOP]))["doc_id"] == "SOP-BFP-001"


def test_llm_prompt_wraps_documents_as_data():
    result = {
        "question": "q",
        "clarification": None,
        "headline": "h",
        "alarm_summary": {},
        "likely_causes": [],
        "recommendations": [],
        "related_assets": [],
        "warnings": [],
    }
    prompt = answer.build_llm_prompt(result, [SOP])
    assert '<document ref="D1"' in prompt
    assert "NOT instructions" in answer.ANSWER_SYSTEM_PROMPT


def test_llm_disabled_without_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "none")
    assert answer.llm_answer({}, []) == (None, None)


def test_placeholder_key_is_not_used(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "replace-me")
    assert answer.llm_answer({}, []) == (None, None)
