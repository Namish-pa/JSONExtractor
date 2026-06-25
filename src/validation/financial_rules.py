from src.domain.purchase_order import PurchaseOrder

TOLERANCE = 0.05  # Rs 0.05 tolerance for floating point rounding

def validate_financial_rules(po: PurchaseOrder) -> list[str]:
    """
    Validates the financial math and summations of the Purchase Order.

    Schema contract (matching real invoice convention):
      lineItem.amount      = quantity * unitPrice          (gross, pre-discount)
      lineItem.discount    = absolute currency discount amount
      lineItem.gst         = absolute currency GST amount on the post-discount subtotal
      lineItem.totalAmount = amount - discount             (post-discount, pre-GST subtotal)
      po.amount            = sum of lineItem.totalAmount   (total pre-GST)
      po.gstAmount         = total GST (may come from footer groupings, not per-line)

    Returns a list of error strings. Empty list means valid.
    """
    errors = []

    calculated_subtotal = 0.0   # sum of (amount - discount) per line
    calculated_gst_amount = 0.0

    for idx, item in enumerate(po.lineItems):
        # Rule 1: amount == quantity * unitPrice  (gross, before discount)
        expected_amount = item.quantity * item.unitPrice
        if abs(expected_amount - item.amount) > TOLERANCE:
            errors.append(
                f"Line Item {idx + 1}: Expected amount {expected_amount:.2f} "
                f"(qty × unitPrice) but got {item.amount:.2f}"
            )

        # Rule 2: totalAmount == amount - discount  (post-discount pre-GST subtotal)
        expected_total = item.amount - item.discount
        if abs(expected_total - item.totalAmount) > TOLERANCE:
            errors.append(
                f"Line Item {idx + 1}: Expected totalAmount {expected_total:.2f} "
                f"(amount - discount) but got {item.totalAmount:.2f}"
            )

        calculated_subtotal += item.totalAmount
        calculated_gst_amount += item.gst

    # Rule 3: po.amount == sum of lineItem.totalAmount (pre-GST total)
    if abs(calculated_subtotal - po.amount) > TOLERANCE:
        errors.append(
            f"Root amount {po.amount:.2f} does not match "
            f"sum of lineItem.totalAmount = {calculated_subtotal:.2f}"
        )

    # Rule 4: Sum of GST grouping amounts == po.gstAmount
    if po.gstGroupings:
        sum_grouping_gst = sum(g.amount for g in po.gstGroupings)
        if abs(sum_grouping_gst - po.gstAmount) > TOLERANCE:
            errors.append(
                f"Root gstAmount {po.gstAmount:.2f} does not match "
                f"sum of GST groupings {sum_grouping_gst:.2f}"
            )

    return errors
