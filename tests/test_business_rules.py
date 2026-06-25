"""
Tests for src/validation/business_rules.py

Covers:
- Happy path (all constraints satisfied)
- po.amount <= 0 → error
- Line item with quantity <= 0 → error
- Line item with negative unitPrice → error
- Line item with negative discount → error
- GST grouping with negative amount → error
- Multiple violations across items
"""

import pytest
from datetime import date
from src.domain.purchase_order import PurchaseOrder, LineItem, GstGrouping
from src.validation.business_rules import validate_business_rules


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def make_line_item(
    product_id: int = 1,
    quantity: float = 2.0,
    unit_price: float = 100.0,
    discount: float = 0.0,
) -> LineItem:
    amount = quantity * unit_price
    total = amount - discount
    return LineItem(
        productId=product_id,
        productName="Widget",
        quantity=quantity,
        unitPrice=unit_price,
        discount=discount,
        amount=amount,
        gst=0.0,
        totalAmount=total,
        typeOfService="GOODS",
    )


def make_po(
    line_items: list[LineItem] | None = None,
    gst_groupings: list[GstGrouping] | None = None,
    po_amount: float = 200.0,
) -> PurchaseOrder:
    if line_items is None:
        line_items = [make_line_item()]
    return PurchaseOrder(
        voucherType="Purchase",
        date=date(2024, 1, 15),
        status="Approved",
        partyLedgerId=10,
        purchaseLedgerId=20,
        gstType="GST",
        amount=po_amount,
        gstAmount=0.0,
        gstGroupings=gst_groupings or [],
        lineItems=line_items,
    )


# ─────────────────────────────────────────────
# Happy-path
# ─────────────────────────────────────────────

class TestBusinessRulesHappyPath:
    def test_valid_po_no_errors(self):
        po = make_po()
        assert validate_business_rules(po) == []

    def test_multiple_valid_line_items_no_errors(self):
        items = [make_line_item(product_id=i) for i in range(1, 4)]
        po = make_po(line_items=items, po_amount=600.0)
        assert validate_business_rules(po) == []

    def test_zero_discount_is_valid(self):
        item = make_line_item(discount=0.0)
        po = make_po(line_items=[item])
        assert validate_business_rules(po) == []


# ─────────────────────────────────────────────
# Rule: po.amount > 0
# ─────────────────────────────────────────────

class TestPOAmountPositive:
    def test_zero_po_amount_raises_error(self):
        po = make_po(po_amount=0.0)
        errors = validate_business_rules(po)
        assert any("total amount must be strictly greater than zero" in e for e in errors)

    def test_negative_po_amount_raises_error(self):
        po = make_po(po_amount=-100.0)
        errors = validate_business_rules(po)
        assert any("total amount must be strictly greater than zero" in e for e in errors)

    def test_positive_po_amount_no_error(self):
        po = make_po(po_amount=0.01)
        errors = validate_business_rules(po)
        amount_errors = [e for e in errors if "total amount" in e]
        assert amount_errors == []


# ─────────────────────────────────────────────
# Rule: line item quantity > 0
# ─────────────────────────────────────────────

class TestLineItemQuantity:
    def test_zero_quantity_raises_error(self):
        item = make_line_item(quantity=0.0)
        po = make_po(line_items=[item])
        errors = validate_business_rules(po)
        assert any("non-positive quantity" in e for e in errors)

    def test_negative_quantity_raises_error(self):
        item = make_line_item(quantity=-1.0)
        po = make_po(line_items=[item])
        errors = validate_business_rules(po)
        assert any("non-positive quantity" in e for e in errors)

    def test_fractional_positive_quantity_no_error(self):
        item = make_line_item(quantity=0.5)
        po = make_po(line_items=[item])
        errors = validate_business_rules(po)
        qty_errors = [e for e in errors if "non-positive quantity" in e]
        assert qty_errors == []


# ─────────────────────────────────────────────
# Rule: line item unitPrice >= 0
# ─────────────────────────────────────────────

class TestLineItemUnitPrice:
    def test_negative_unit_price_raises_error(self):
        item = make_line_item(unit_price=-50.0)
        po = make_po(line_items=[item])
        errors = validate_business_rules(po)
        assert any("negative unit price" in e for e in errors)

    def test_zero_unit_price_no_error(self):
        """Free items (price=0) should be allowed."""
        item = make_line_item(unit_price=0.0)
        po = make_po(line_items=[item])
        errors = validate_business_rules(po)
        price_errors = [e for e in errors if "negative unit price" in e]
        assert price_errors == []


# ─────────────────────────────────────────────
# Rule: line item discount >= 0
# ─────────────────────────────────────────────

class TestLineItemDiscount:
    def test_negative_discount_raises_error(self):
        item = make_line_item(discount=-5.0)
        po = make_po(line_items=[item])
        errors = validate_business_rules(po)
        assert any("negative discount" in e for e in errors)

    def test_positive_discount_no_error(self):
        item = make_line_item(discount=20.0)
        po = make_po(line_items=[item])
        errors = validate_business_rules(po)
        discount_errors = [e for e in errors if "negative discount" in e]
        assert discount_errors == []


# ─────────────────────────────────────────────
# Rule: gst grouping amount >= 0
# ─────────────────────────────────────────────

class TestGstGroupingAmount:
    def test_negative_gst_grouping_amount_raises_error(self):
        groupings = [
            GstGrouping(gstPercentage="18%", amount=-10.0, gstType="CGST", ledgerId=1)
        ]
        po = make_po(gst_groupings=groupings)
        errors = validate_business_rules(po)
        assert any("negative amount" in e for e in errors)

    def test_zero_gst_grouping_amount_no_error(self):
        groupings = [
            GstGrouping(gstPercentage="0%", amount=0.0, gstType="Exempt", ledgerId=1)
        ]
        po = make_po(gst_groupings=groupings)
        errors = validate_business_rules(po)
        gst_errors = [e for e in errors if "negative amount" in e]
        assert gst_errors == []


# ─────────────────────────────────────────────
# Multiple simultaneous violations
# ─────────────────────────────────────────────

class TestMultipleBusinessRuleViolations:
    def test_all_violations_at_once(self):
        bad_item = make_line_item(quantity=-1.0, unit_price=-5.0, discount=-1.0)
        bad_grouping = GstGrouping(gstPercentage="18%", amount=-1.0, gstType="CGST", ledgerId=1)
        po = make_po(line_items=[bad_item], gst_groupings=[bad_grouping], po_amount=-100.0)
        errors = validate_business_rules(po)
        # Should have: PO amount, quantity, unit price, discount, gst amount = 5 errors
        assert any("total amount" in e for e in errors)
        assert any("non-positive quantity" in e for e in errors)
        assert any("negative unit price" in e for e in errors)
        assert any("negative discount" in e for e in errors)
        assert any("negative amount" in e for e in errors)

    def test_error_reports_correct_product_id(self):
        items = [
            make_line_item(product_id=42, quantity=-3.0),
        ]
        po = make_po(line_items=items)
        errors = validate_business_rules(po)
        assert any("Product 42" in e for e in errors)
