"""
Tests for src/validation/financial_rules.py

Covers:
- Happy path (all math correct)
- Rule 1: unitPrice * quantity != amount
- Rule 2: amount - discount != totalAmount  (totalAmount is post-discount pre-GST)
- Rule 3: Sum of lineItem.totalAmount != po.amount
- Rule 4: Sum of gstGroupings.amount != po.gstAmount
- Tolerance boundary checks (exactly at 0.05 vs just over)
- Multiple simultaneous errors
"""

import pytest
from datetime import date
from src.domain.purchase_order import PurchaseOrder, LineItem, GstGrouping
from src.validation.financial_rules import validate_financial_rules, TOLERANCE


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def make_line_item(
    quantity: float = 2.0,
    unit_price: float = 100.0,
    discount: float = 10.0,
    gst: float = 18.0,
    amount: float | None = None,        # defaults to quantity * unit_price
    total_amount: float | None = None,  # defaults to amount - discount (pre-GST)
) -> LineItem:
    computed_amount = quantity * unit_price
    if amount is None:
        amount = computed_amount
    if total_amount is None:
        total_amount = amount - discount  # post-discount, pre-GST subtotal
    return LineItem(
        productId=1,
        productName="Widget",
        quantity=quantity,
        unitPrice=unit_price,
        discount=discount,
        amount=amount,
        gst=gst,
        totalAmount=total_amount,
        typeOfService="GOODS",
    )


def make_po(
    line_items: list[LineItem] | None = None,
    gst_groupings: list[GstGrouping] | None = None,
    po_amount: float | None = None,
    po_gst_amount: float = 18.0,
) -> PurchaseOrder:
    if line_items is None:
        line_items = [make_line_item()]
    if gst_groupings is None:
        gst_groupings = []
    if po_amount is None:
        po_amount = sum(item.totalAmount for item in line_items)
    return PurchaseOrder(
        voucherType="Purchase",
        date=date(2024, 1, 15),
        status="Approved",
        partyLedgerId=10,
        purchaseLedgerId=20,
        gstType="GST",
        amount=po_amount,
        gstAmount=po_gst_amount,
        gstGroupings=gst_groupings or [],
        lineItems=line_items,
    )


# ─────────────────────────────────────────────
# Happy-path tests
# ─────────────────────────────────────────────

class TestFinancialRulesHappyPath:
    def test_single_valid_line_item_returns_no_errors(self):
        """A perfectly balanced PO produces zero validation errors."""
        po = make_po()
        assert validate_financial_rules(po) == []

    def test_multiple_valid_line_items_returns_no_errors(self):
        items = [
            make_line_item(quantity=3.0, unit_price=50.0, discount=5.0, gst=9.0),
            make_line_item(quantity=1.0, unit_price=200.0, discount=0.0, gst=36.0),
        ]
        po = make_po(line_items=items)
        assert validate_financial_rules(po) == []

    def test_valid_gst_groupings_no_errors(self):
        """When gstGroupings sum matches po.gstAmount, no error is raised."""
        items = [make_line_item(gst=18.0)]
        groupings = [
            GstGrouping(gstPercentage="18%", amount=18.0, gstType="CGST", ledgerId=1)
        ]
        po = make_po(line_items=items, gst_groupings=groupings, po_gst_amount=18.0)
        assert validate_financial_rules(po) == []

    def test_empty_line_items_zero_po_amount(self):
        """An empty PO (no line items) with amount=0 is internally consistent."""
        po = make_po(line_items=[], po_amount=0.0, po_gst_amount=0.0)
        assert validate_financial_rules(po) == []


# ─────────────────────────────────────────────
# Rule 1: unitPrice * quantity == amount
# ─────────────────────────────────────────────

class TestRule1UnitPriceTimesQuantity:
    def test_wrong_amount_raises_error(self):
        item = make_line_item(quantity=2.0, unit_price=100.0, amount=150.0)
        po = make_po(line_items=[item], po_amount=item.totalAmount)
        errors = validate_financial_rules(po)
        assert any("Expected amount" in e and "Line Item 1" in e for e in errors)

    def test_amount_within_tolerance_no_error(self):
        """Deviation exactly at TOLERANCE boundary (0.04) should pass."""
        item = make_line_item(quantity=2.0, unit_price=100.0, amount=200.04)
        po = make_po(line_items=[item], po_amount=item.totalAmount)
        errors = validate_financial_rules(po)
        rule1_errors = [e for e in errors if "Expected amount" in e]
        assert rule1_errors == []

    def test_amount_just_over_tolerance_raises_error(self):
        """Deviation of exactly TOLERANCE + epsilon (0.06) must fail."""
        item = make_line_item(quantity=2.0, unit_price=100.0, amount=200.06)
        po = make_po(line_items=[item], po_amount=item.totalAmount)
        errors = validate_financial_rules(po)
        assert any("Expected amount" in e for e in errors)

    def test_second_line_item_error_is_labeled_correctly(self):
        valid_item = make_line_item()
        bad_item = make_line_item(quantity=1.0, unit_price=50.0, amount=99.0)
        po = make_po(line_items=[valid_item, bad_item], po_amount=valid_item.totalAmount + bad_item.totalAmount)
        errors = validate_financial_rules(po)
        assert any("Line Item 2" in e and "Expected amount" in e for e in errors)


# ─────────────────────────────────────────────
# Rule 2: amount - discount == totalAmount  (post-discount, pre-GST subtotal)
# ─────────────────────────────────────────────

class TestRule2TotalAmount:
    def test_wrong_total_amount_raises_error(self):
        # totalAmount = 999 but expected 200 - 10 = 190
        item = make_line_item(amount=200.0, gst=18.0, discount=10.0, total_amount=999.0)
        po = make_po(line_items=[item], po_amount=999.0)
        errors = validate_financial_rules(po)
        assert any("Expected totalAmount" in e and "Line Item 1" in e for e in errors)

    def test_correct_total_amount_no_error(self):
        # amount=200, discount=10 → totalAmount = 190 (pre-GST)
        item = make_line_item(amount=200.0, gst=18.0, discount=10.0, total_amount=190.0)
        po = make_po(line_items=[item], po_amount=190.0)
        errors = validate_financial_rules(po)
        rule2_errors = [e for e in errors if "Expected totalAmount" in e]
        assert rule2_errors == []

    def test_total_amount_within_tolerance_no_error(self):
        # 190.04 is within 0.05 of 190.0
        item = make_line_item(amount=200.0, gst=18.0, discount=10.0, total_amount=190.04)
        po = make_po(line_items=[item], po_amount=190.04)
        errors = validate_financial_rules(po)
        rule2_errors = [e for e in errors if "Expected totalAmount" in e]
        assert rule2_errors == []

    def test_total_amount_over_tolerance_raises_error(self):
        # 190.06 exceeds 0.05 from 190.0 → should fail
        item = make_line_item(amount=200.0, gst=18.0, discount=10.0, total_amount=190.06)
        po = make_po(line_items=[item], po_amount=190.06)
        errors = validate_financial_rules(po)
        assert any("Expected totalAmount" in e for e in errors)


# ─────────────────────────────────────────────
# Rule 3: Sum of lineItems.totalAmount == po.amount
# ─────────────────────────────────────────────

class TestRule3RootAmount:
    def test_wrong_root_amount_raises_error(self):
        items = [make_line_item(), make_line_item()]
        # correct sum would be 2 * (200 + 18 - 10) = 416
        po = make_po(line_items=items, po_amount=999.0)
        errors = validate_financial_rules(po)
        assert any("Root amount" in e for e in errors)

    def test_correct_root_amount_no_error(self):
        items = [make_line_item(), make_line_item()]
        correct_sum = sum(i.totalAmount for i in items)
        po = make_po(line_items=items, po_amount=correct_sum)
        errors = validate_financial_rules(po)
        root_errors = [e for e in errors if "Root amount" in e]
        assert root_errors == []


# ─────────────────────────────────────────────
# Rule 4: Sum of GST groupings == po.gstAmount
# ─────────────────────────────────────────────

class TestRule4GstGroupings:
    def test_wrong_gst_grouping_sum_raises_error(self):
        groupings = [
            GstGrouping(gstPercentage="18%", amount=10.0, gstType="CGST", ledgerId=1),
            GstGrouping(gstPercentage="18%", amount=10.0, gstType="SGST", ledgerId=2),
        ]
        po = make_po(gst_groupings=groupings, po_gst_amount=999.0)
        errors = validate_financial_rules(po)
        assert any("Root gstAmount" in e for e in errors)

    def test_correct_gst_grouping_sum_no_error(self):
        groupings = [
            GstGrouping(gstPercentage="9%", amount=9.0, gstType="CGST", ledgerId=1),
            GstGrouping(gstPercentage="9%", amount=9.0, gstType="SGST", ledgerId=2),
        ]
        po = make_po(gst_groupings=groupings, po_gst_amount=18.0)
        errors = validate_financial_rules(po)
        gst_errors = [e for e in errors if "Root gstAmount" in e]
        assert gst_errors == []

    def test_empty_gst_groupings_skips_rule4(self):
        """Rule 4 is only applied when gstGroupings is non-empty."""
        po = make_po(gst_groupings=[], po_gst_amount=0.0)
        errors = validate_financial_rules(po)
        gst_errors = [e for e in errors if "Root gstAmount" in e]
        assert gst_errors == []

    def test_gst_groupings_within_tolerance_no_error(self):
        groupings = [
            GstGrouping(gstPercentage="18%", amount=18.04, gstType="GST", ledgerId=1)
        ]
        po = make_po(gst_groupings=groupings, po_gst_amount=18.0)
        errors = validate_financial_rules(po)
        gst_errors = [e for e in errors if "Root gstAmount" in e]
        assert gst_errors == []


# ─────────────────────────────────────────────
# Multiple simultaneous errors
# ─────────────────────────────────────────────

class TestMultipleErrors:
    def test_multiple_errors_all_reported(self):
        """All four rule violations should be present in a single bad PO."""
        bad_item = LineItem(
            productId=1,
            productName="Bad Widget",
            quantity=2.0,
            unitPrice=100.0,
            discount=10.0,
            amount=150.0,        # wrong: should be 200 (qty * unitPrice)
            gst=18.0,
            totalAmount=999.0,   # wrong: should be 140 (150 - 10, pre-GST)
            typeOfService="GOODS",
        )
        groupings = [
            GstGrouping(gstPercentage="18%", amount=1.0, gstType="GST", ledgerId=1)
        ]
        po = PurchaseOrder(
            voucherType="Purchase",
            date=date(2024, 1, 15),
            status="Approved",
            partyLedgerId=10,
            purchaseLedgerId=20,
            gstType="GST",
            amount=1.0,       # wrong root amount
            gstAmount=999.0,  # wrong gst amount
            gstGroupings=groupings,
            lineItems=[bad_item],
        )
        errors = validate_financial_rules(po)
        assert any("Expected amount" in e for e in errors)
        assert any("Expected totalAmount" in e for e in errors)
        assert any("Root amount" in e for e in errors)
        assert any("Root gstAmount" in e for e in errors)
