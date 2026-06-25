"""
Tests for src/application/orchestrators.py (PurchaseOrderExtractionWorkflow)

Uses unittest.mock to replace the PDF extractor and LLM extractor so no
real external calls are made.

Covers:
- Successful end-to-end path (returns PO dict)
- Extractor raises exception → extraction_failed
- Extractor returns empty text → no_text_found
- LLM raises exception → llm_extraction_failed
- Validation errors → validation_failed with partial_data
- Valid PO with no errors returns clean dict
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import date

from src.application.orchestrators import PurchaseOrderExtractionWorkflow
from src.domain.purchase_order import PurchaseOrder, LineItem, GstGrouping


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

def _make_valid_po() -> PurchaseOrder:
    """Builds a financially and business-rule-valid PurchaseOrder.
    
    Schema: totalAmount = amount - discount (post-discount, pre-GST subtotal)
    """
    item = LineItem(
        productId=1,
        productName="Test Widget",
        quantity=2.0,
        unitPrice=100.0,
        discount=0.0,
        amount=200.0,
        gst=36.0,
        totalAmount=200.0,   # amount - discount = 200 - 0
        typeOfService="GOODS",
    )
    return PurchaseOrder(
        voucherType="Purchase",
        date=date(2024, 1, 15),
        status="Approved",
        partyLedgerId=10,
        purchaseLedgerId=20,
        gstType="GST",
        amount=200.0,        # sum of lineItem.totalAmount
        gstAmount=36.0,
        gstGroupings=[
            GstGrouping(gstPercentage="18%", amount=36.0, gstType="GST", ledgerId=99)
        ],
        lineItems=[item],
    )


def _make_workflow(extracted_text: str, llm_return: PurchaseOrder | Exception):
    """Creates a workflow with mocked extractor and LLM."""
    mock_extractor = MagicMock()
    mock_llm = MagicMock()

    if isinstance(llm_return, Exception):
        mock_llm.extract_purchase_order.side_effect = llm_return
    else:
        mock_llm.extract_purchase_order.return_value = llm_return

    mock_extractor.extract_text.return_value = extracted_text
    return PurchaseOrderExtractionWorkflow(mock_extractor, mock_llm)


# ─────────────────────────────────────────────
# Extractor Stage
# ─────────────────────────────────────────────

class TestExtractionStage:
    def test_extractor_exception_returns_extraction_failed(self):
        mock_extractor = MagicMock()
        mock_extractor.extract_text.side_effect = ValueError("corrupt pdf")
        workflow = PurchaseOrderExtractionWorkflow(mock_extractor, MagicMock())
        result = workflow.execute(b"dummy bytes")
        assert result["error"] == "extraction_failed"
        assert "corrupt pdf" in result["details"]

    def test_empty_text_returns_no_text_found(self):
        workflow = _make_workflow(extracted_text="   ", llm_return=_make_valid_po())
        result = workflow.execute(b"dummy bytes")
        assert result["error"] == "no_text_found"

    def test_whitespace_only_text_returns_no_text_found(self):
        workflow = _make_workflow(extracted_text="\n\t\n", llm_return=_make_valid_po())
        result = workflow.execute(b"dummy bytes")
        assert result["error"] == "no_text_found"

    def test_extractor_called_with_provided_bytes(self):
        mock_extractor = MagicMock()
        mock_extractor.extract_text.return_value = "some text"
        mock_llm = MagicMock()
        mock_llm.extract_purchase_order.return_value = _make_valid_po()
        workflow = PurchaseOrderExtractionWorkflow(mock_extractor, mock_llm)
        workflow.execute(b"my pdf bytes")
        mock_extractor.extract_text.assert_called_once_with(b"my pdf bytes")


# ─────────────────────────────────────────────
# LLM Stage
# ─────────────────────────────────────────────

class TestLLMStage:
    def test_llm_exception_returns_llm_extraction_failed(self):
        workflow = _make_workflow(
            extracted_text="PO text content",
            llm_return=RuntimeError("model overloaded"),
        )
        result = workflow.execute(b"bytes")
        assert result["error"] == "llm_extraction_failed"
        assert "model overloaded" in result["details"]

    def test_llm_called_with_extracted_text(self):
        mock_extractor = MagicMock()
        mock_extractor.extract_text.return_value = "extracted po text"
        mock_llm = MagicMock()
        mock_llm.extract_purchase_order.return_value = _make_valid_po()
        workflow = PurchaseOrderExtractionWorkflow(mock_extractor, mock_llm)
        workflow.execute(b"bytes")
        mock_llm.extract_purchase_order.assert_called_once_with("extracted po text")


# ─────────────────────────────────────────────
# Validation Stage
# ─────────────────────────────────────────────

class TestValidationStage:
    def test_validation_failure_returns_422_payload(self):
        # A PO with amount=0 triggers business rule violation
        invalid_po = _make_valid_po()
        invalid_po.amount = -999.0  # violates business rule
        workflow = _make_workflow("po text", invalid_po)
        result = workflow.execute(b"bytes")
        assert result["error"] == "validation_failed"
        assert "details" in result
        assert isinstance(result["details"], list)
        assert len(result["details"]) > 0

    def test_validation_failure_includes_partial_data(self):
        invalid_po = _make_valid_po()
        invalid_po.amount = -1.0
        workflow = _make_workflow("po text", invalid_po)
        result = workflow.execute(b"bytes")
        assert "partial_data" in result
        # partial_data should be a dict (serialized PO)
        assert isinstance(result["partial_data"], dict)

    def test_financially_invalid_po_returns_validation_failed(self):
        """PO where lineItem amount is wrong should fail financial validation."""
        po = _make_valid_po()
        # Tamper with the amount field so Rule 1 fails
        po.lineItems[0].amount = 1.0
        workflow = _make_workflow("po text", po)
        result = workflow.execute(b"bytes")
        assert result["error"] == "validation_failed"


# ─────────────────────────────────────────────
# Success Path
# ─────────────────────────────────────────────

class TestSuccessPath:
    def test_valid_po_returns_serialized_dict(self):
        po = _make_valid_po()
        workflow = _make_workflow("po text", po)
        result = workflow.execute(b"bytes")
        # Should NOT have an error key
        assert "error" not in result

    def test_valid_po_result_contains_expected_fields(self):
        po = _make_valid_po()
        workflow = _make_workflow("po text", po)
        result = workflow.execute(b"bytes")
        assert result["voucherType"] == "Purchase"
        assert result["amount"] == 200.0
        assert len(result["lineItems"]) == 1

    def test_valid_po_line_item_fields_intact(self):
        po = _make_valid_po()
        workflow = _make_workflow("po text", po)
        result = workflow.execute(b"bytes")
        li = result["lineItems"][0]
        assert li["productName"] == "Test Widget"
        assert li["quantity"] == 2.0
        assert li["unitPrice"] == 100.0
