import pytest
from app.db.models import Document, Obligation

def test_explain_obligation_endpoint(client, db_session):
    doc = Document(
        id="doc_test_explain",
        title="SEBI Circular on System Access",
        circular_number="SEBI/HO/2026/01",
        content_hash="hash123",
        status="parsed",
    )
    db_session.add(doc)
    db_session.flush()

    ob = Obligation(
        id="ob_test_explain",
        source_document_id=doc.id,
        clause_path="1.2",
        verbatim_text="shall enable access to the respective listed company on the portal/ platform.",
        normalized_statement="The Designated Depository must enable access to the respective listed company on the portal/platform.",
        modality="shall",
        status="verified",
        deadline_or_periodicity="continuous",
        threshold=None,
    )
    db_session.add(ob)
    db_session.commit()

    res = client.post(f"/obligations/{ob.id}/explain")
    assert res.status_code == 200
    data = res.json()

    assert "simple_summary" in data
    assert "key_actions" in data
    assert isinstance(data["key_actions"], list)
    assert len(data["key_actions"]) > 0
    assert "who_applies" in data
    assert "why_it_matters" in data
