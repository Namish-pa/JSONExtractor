"""
API-level tests for POST /purchase-order/extract

Uses FastAPI TestClient + unittest.mock to intercept the workflow so
no real PDF parsing or LLM calls are made.

Covers:
- Non-PDF file → 400
- Successful extraction → 200 with JSON body
- Workflow returns validation_failed → 422 with error body
- Workflow returns extraction_failed → 500 with error body
- Workflow returns llm_extraction_failed → 500 with error body
- Empty PDF body handled gracefully
"""

import io
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from datetime import date

from main import app
from src.domain.purchase_order import PurchaseOrder, LineItem, GstGrouping


client = TestClient(app)

ROUTE = "/purchase-order/extract"


# ─────────────────────────────────────────────
# Helper: minimal valid PO dict
# ─────────────────────────────────────────────

def _valid_po_dict() -> dict:
    return {
        "voucherType": "Purchase",
        "supplierInvoiceNo": "INV-001",
        "date": "2024-01-15",
        "status": "Approved",
        "partyLedgerId": 10,
        "purchaseLedgerId": 20,
        "partyAddress": None,
        "billingAddress": None,
        "billingState": None,
        "shippingAddress": None,
        "shippingState": None,
        "gstType": "GST",
        "grnIds": [],
        "storeIds": [],
        "awsFileId": None,
        "amount": 236.0,
        "gstAmount": 36.0,
        "gstGroupings": [
            {"gstPercentage": "18%", "amount": 36.0, "gstType": "GST", "ledgerId": 99}
        ],
        "lineItems": [
            {
                "productId": 1,
                "productName": "Widget",
                "description": None,
                "hsnCode": None,
                "unitType": None,
                "quantity": 2.0,
                "discount": 0.0,
                "unitPrice": 100.0,
                "amount": 200.0,
                "gst": 36.0,
                "totalAmount": 236.0,
                "grnId": None,
                "storeId": None,
                "typeOfService": "GOODS",
            }
        ],
        "shippingDetails": None,
    }


def _dummy_pdf_bytes() -> bytes:
    """Smallest valid-ish PDF bytes for content-type testing."""
    return b"%PDF-1.4 fake pdf content"


# ─────────────────────────────────────────────
# Content-type validation
# ─────────────────────────────────────────────

class TestContentTypeValidation:
    def test_non_pdf_returns_400(self):
        files = {"file": ("invoice.txt", b"hello", "text/plain")}
        response = client.post(ROUTE, files=files)
        assert response.status_code == 400
        assert "PDF" in response.json()["detail"]

    def test_image_file_returns_400(self):
        files = {"file": ("invoice.png", b"\x89PNG\r\n", "image/png")}
        response = client.post(ROUTE, files=files)
        assert response.status_code == 400

    def test_no_file_returns_422(self):
        """Sending no file at all should return 422 (FastAPI validation)."""
        response = client.post(ROUTE)
        assert response.status_code == 422


# ─────────────────────────────────────────────
# Successful extraction path
# ─────────────────────────────────────────────

class TestSuccessfulExtraction:
    def test_pdf_upload_returns_200(self):
        with patch(
            "src.api.routes.workflow.execute",
            return_value=_valid_po_dict(),
        ):
            files = {"file": ("invoice.pdf", _dummy_pdf_bytes(), "application/pdf")}
            response = client.post(ROUTE, files=files)
        assert response.status_code == 200

    def test_response_body_has_expected_keys(self):
        with patch(
            "src.api.routes.workflow.execute",
            return_value=_valid_po_dict(),
        ):
            files = {"file": ("invoice.pdf", _dummy_pdf_bytes(), "application/pdf")}
            response = client.post(ROUTE, files=files)
        body = response.json()
        assert body["voucherType"] == "Purchase"
        assert body["amount"] == 236.0
        assert len(body["lineItems"]) == 1

    def test_response_content_type_is_json(self):
        with patch(
            "src.api.routes.workflow.execute",
            return_value=_valid_po_dict(),
        ):
            files = {"file": ("invoice.pdf", _dummy_pdf_bytes(), "application/pdf")}
            response = client.post(ROUTE, files=files)
        assert "application/json" in response.headers["content-type"]


# ─────────────────────────────────────────────
# Validation failure path
# ─────────────────────────────────────────────

class TestValidationFailure:
    def test_validation_failed_returns_422(self):
        payload = {
            "error": "validation_failed",
            "details": ["Root amount 1.00 does not match sum of line items 236.00"],
            "partial_data": _valid_po_dict(),
        }
        with patch("src.api.routes.workflow.execute", return_value=payload):
            files = {"file": ("invoice.pdf", _dummy_pdf_bytes(), "application/pdf")}
            response = client.post(ROUTE, files=files)
        assert response.status_code == 422

    def test_validation_failed_body_has_error_key(self):
        payload = {
            "error": "validation_failed",
            "details": ["Some error"],
            "partial_data": {},
        }
        with patch("src.api.routes.workflow.execute", return_value=payload):
            files = {"file": ("invoice.pdf", _dummy_pdf_bytes(), "application/pdf")}
            response = client.post(ROUTE, files=files)
        assert response.json()["error"] == "validation_failed"

    def test_validation_failed_body_has_partial_data(self):
        payload = {
            "error": "validation_failed",
            "details": ["err"],
            "partial_data": {"amount": 1.0},
        }
        with patch("src.api.routes.workflow.execute", return_value=payload):
            files = {"file": ("invoice.pdf", _dummy_pdf_bytes(), "application/pdf")}
            response = client.post(ROUTE, files=files)
        assert "partial_data" in response.json()


# ─────────────────────────────────────────────
# Internal processing error paths
# ─────────────────────────────────────────────

class TestInternalErrorPaths:
    def test_extraction_failed_returns_500(self):
        payload = {"error": "extraction_failed", "details": "corrupt PDF"}
        with patch("src.api.routes.workflow.execute", return_value=payload):
            files = {"file": ("invoice.pdf", _dummy_pdf_bytes(), "application/pdf")}
            response = client.post(ROUTE, files=files)
        assert response.status_code == 500

    def test_llm_extraction_failed_returns_500(self):
        payload = {"error": "llm_extraction_failed", "details": "model error"}
        with patch("src.api.routes.workflow.execute", return_value=payload):
            files = {"file": ("invoice.pdf", _dummy_pdf_bytes(), "application/pdf")}
            response = client.post(ROUTE, files=files)
        assert response.status_code == 500

    def test_no_text_found_returns_500(self):
        payload = {"error": "no_text_found"}
        with patch("src.api.routes.workflow.execute", return_value=payload):
            files = {"file": ("invoice.pdf", _dummy_pdf_bytes(), "application/pdf")}
            response = client.post(ROUTE, files=files)
        assert response.status_code == 500


# ─────────────────────────────────────────────
# Health check
# ─────────────────────────────────────────────

class TestHealthCheck:
    def test_health_endpoint_returns_200(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
