from src.domain.purchase_order import PurchaseOrder

TOLERANCE = 0.05 # 5 cents tolerance for floating point math or rounding

def validate_financial_rules(po: PurchaseOrder) -> list[str]:
    """
    Validates the financial math and summations of the Purchase Order.
    Returns a list of error strings. Empty list means valid.
    """
    errors = []
    
    calculated_total_amount = 0.0
    calculated_gst_amount = 0.0
    
    for idx, item in enumerate(po.lineItems):
        # Rule 1: unitPrice * quantity == amount (roughly)
        # Note: Depending on the system, discount might be subtracted before this 'amount'.
        # Assuming schema implies: amount = quantity * unitPrice
        expected_amount = item.quantity * item.unitPrice
        if abs(expected_amount - item.amount) > TOLERANCE:
            errors.append(f"Line Item {idx + 1}: Expected amount {expected_amount:.2f} but got {item.amount:.2f}")
            
        # Rule 2: amount + gst - discount == totalAmount
        expected_total = item.amount + item.gst - item.discount
        if abs(expected_total - item.totalAmount) > TOLERANCE:
            errors.append(f"Line Item {idx + 1}: Expected totalAmount {expected_total:.2f} but got {item.totalAmount:.2f}")
            
        calculated_total_amount += item.totalAmount
        calculated_gst_amount += item.gst

    # Rule 3: Sum of line item totalAmount == root amount
    if abs(calculated_total_amount - po.amount) > TOLERANCE:
        errors.append(f"Root amount {po.amount:.2f} does not match sum of line items {calculated_total_amount:.2f}")
        
    # Rule 4: Sum of GST Groupings == root gstAmount
    sum_grouping_gst = sum(g.amount for g in po.gstGroupings)
    if po.gstGroupings and abs(sum_grouping_gst - po.gstAmount) > TOLERANCE:
         errors.append(f"Root gstAmount {po.gstAmount:.2f} does not match sum of GST groupings {sum_grouping_gst:.2f}")

    return errors
