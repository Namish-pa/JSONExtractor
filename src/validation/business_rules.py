from src.domain.purchase_order import PurchaseOrder

def validate_business_rules(po: PurchaseOrder) -> list[str]:
    """
    Validates general business rules for the Purchase Order.
    Returns a list of error strings. Empty list means valid.
    """
    errors = []
    
    if po.amount <= 0:
        errors.append("Purchase Order total amount must be strictly greater than zero.")
        
    for idx, item in enumerate(po.lineItems):
        if item.quantity <= 0:
            errors.append(f"Line Item {idx + 1} (Product {item.productId}) has non-positive quantity: {item.quantity}")
        if item.unitPrice < 0:
            errors.append(f"Line Item {idx + 1} (Product {item.productId}) has negative unit price: {item.unitPrice}")
        if item.discount < 0:
            errors.append(f"Line Item {idx + 1} (Product {item.productId}) has negative discount: {item.discount}")
            
    # Check that gstGroupings have valid percentages (assuming standard strings like "18%", "5%", or floats)
    for idx, grouping in enumerate(po.gstGroupings):
        if grouping.amount < 0:
            errors.append(f"GST Grouping {idx + 1} has negative amount: {grouping.amount}")
            
    return errors
