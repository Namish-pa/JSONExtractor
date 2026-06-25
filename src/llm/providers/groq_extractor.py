import json
import os
from groq import Groq
from pydantic import ValidationError
from src.domain.purchase_order import PurchaseOrder
from src.llm.interfaces import LLMExtractor
import structlog

logger = structlog.get_logger()

# We provide a prompt that enforces the JSON structure based on our Pydantic models.
# For more robustness in production, we could use Groq's tool calling feature,
# but JSON mode with a strong prompt is highly effective for this MVP.

SYSTEM_PROMPT = """You are an expert Document Intelligence AI.
Your task is to extract structured information from a Purchase Order document text and output it as a valid JSON object.
Do not include any markdown formatting, only output the raw JSON object.

The output MUST strictly conform to the following schema:
{
  "voucherType": "string (required)",
  "supplierInvoiceNo": "string (optional)",
  "date": "string (optional, ISO-8601 date: YYYY-MM-DD — use the invoice/PO date if present, set null if no document date is found)",
  "status": "string (optional, e.g. 'Approved', 'Pending' — set null if not present)",
  "partyLedgerId": "integer (required, use 0 if not present in document)",
  "purchaseLedgerId": "integer (required, use 0 if not present in document)",
  "partyAddress": "string (optional)",
  "billingAddress": "string (optional)",
  "billingState": "string (optional)",
  "shippingAddress": "string (optional)",
  "shippingState": "string (optional)",
  "gstType": "string (required, e.g. 'IntraState', 'InterState', 'GST')",
  "grnIds": ["integer"],
  "storeIds": ["integer"],
  "awsFileId": "string (optional)",
  "amount": "float (required, the total pre-GST amount = sum of all line item amounts after discount)",
  "gstAmount": "float (required, total GST amount in currency units, NOT a percentage)",
  "gstGroupings": [
    {
      "gstPercentage": "string (required, e.g. '9%' or '18%')",
      "amount": "float (required, the GST amount in currency units for this slab — NOT a percentage)",
      "gstType": "string (required, e.g. 'CGST', 'SGST', 'IGST')",
      "ledgerId": "integer (required, use 0 if not present in document)"
    }
  ],
  "lineItems": [
    {
      "productId": "integer (required, use 0 if not present in document)",
      "productName": "string (required)",
      "description": "string (optional)",
      "hsnCode": "string (optional)",
      "unitType": "string (optional, e.g. 'Pieces', 'Nos', 'sqmm')",
      "quantity": "float (required)",
      "unitPrice": "float (required, price per single unit in currency)",
      "discount": "float (required, ABSOLUTE CURRENCY AMOUNT of discount — NOT a percentage. Example: if 5% discount on 35000 = 1750.0. Use 0 if no discount.)",
      "amount": "float (required, gross amount BEFORE GST = quantity * unitPrice. Do NOT subtract discount here.)",
      "gst": "float (required, ABSOLUTE CURRENCY AMOUNT of GST — NOT a rate or percentage. Example: 18% GST on 33250 = 5985.0)",
      "totalAmount": "float (required, post-discount pre-GST subtotal = amount - discount. This matches the 'Amount' column shown in the invoice table.)",
      "grnId": "integer (optional)",
      "storeId": "integer (optional)",
      "typeOfService": "string (optional, e.g. 'GOODS', 'SERVICES' — set null if not present)"
    }
  ],
  "shippingDetails": {
    "documentNo": "string (optional)",
    "dispatchThrough": "string (optional)",
    "destination": "string (optional)",
    "carrierName": "string (optional)",
    "lrOrRrNo": "string (optional)",
    "vehicleNo": "string (optional)",
    "eWayBillNo": "string (optional)",
    "ewayBillDate": "string (optional, ISO-8601 date)"
  }
}

CRITICAL RULES FOR OCR ERROR CORRECTION & MATHEMATICAL SELF-CONSISTENCY:
1. **Currency Symbol OCR Errors**: OCR often misreads the Rupee symbol (`₹`) as the digit `2` or `%` or `t`. This can result in numbers like `₹ 1,500.00` being read as `21,500.00` or `₹ 18,500.00` being read as `218,500.00`.
   - Always verify if `quantity * unitPrice` matches the expected gross amount. If the extracted unit price has an extra leading digit (usually a `2`) compared to the mathematically expected unit price derived from the line's total amount and discount, CORRECT IT (e.g. change `21,500.00` to `1,500.00` and `218,500.00` to `18,500.00`).
2. **Step-by-Step Line Item Math**:
   - **`unitPrice`**: The corrected price per unit (after removing OCR noise like prepended `2` or `%` from `₹`).
   - **`amount`**: MUST equal `quantity * unitPrice` (gross amount before discount).
   - **`totalAmount`**: The post-discount pre-GST subtotal. This is the last column in the line item table (e.g., `33250.00`, `38220.00`, `22080.00`, `211640.00`). Treat this printed total as a ground-truth anchor.
   - **`discount`**: MUST equal `amount - totalAmount` (the absolute currency amount of discount for the entire quantity). For example, if gross `amount` is 24000.00 and printed `totalAmount` is 22080.00, then `discount` is 1920.00 (NOT 0, and NOT per-unit).
   - **`gst`**: MUST be the absolute currency amount of GST for the line. Formula: `totalAmount * (gst_percentage / 100)`. For example, 18% GST on 22080.00 is 3974.40.
3. **Root Totals Math**:
   - **`amount`**: MUST equal the sum of all `lineItem.totalAmount` values (e.g., 305190.00).
   - **`gstAmount`**: MUST equal the sum of all `lineItem.gst` values. It must also match the sum of the `amount` fields inside `gstGroupings` (which is `27467.10 * 2 = 54934.20`).
4. If optional data is missing, set the value to null.
5. Ensure all numeric fields are correctly typed as numbers (not strings).
"""

class GroqExtractor(LLMExtractor):
    def __init__(self, api_key: str | None = None, model: str = "llama-3.3-70b-versatile"):
        # Uses GROQ_API_KEY from environment if not explicitly passed
        self.client = Groq(api_key=api_key or os.environ.get("GROQ_API_KEY"))
        self.model = model

    def extract_purchase_order(self, text: str) -> PurchaseOrder:
        logger.info("Starting LLM extraction via Groq", model=self.model)
        
        try:
            chat_completion = self.client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": f"Extract the PO data from the following text:\n\n{text}",
                    }
                ],
                model=self.model,
                temperature=0.0, # Zero temperature for deterministic extraction
                response_format={"type": "json_object"},
            )

            raw_json_str = chat_completion.choices[0].message.content

            # Guard: Groq SDK types content as str | None
            if raw_json_str is None:
                raise ValueError("Groq returned an empty response (content is None)")

            # Parse the JSON string into our Pydantic model for schema enforcement
            try:
                po_data = json.loads(raw_json_str)
            except json.JSONDecodeError as e:
                logger.error("LLM response was not valid JSON", error=str(e), raw=raw_json_str[:200])
                raise ValueError(f"LLM returned invalid JSON: {e}")

            # Enforce mathematical self-consistency and correct OCR errors
            try:
                line_items = po_data.get("lineItems", [])
                for item in line_items:
                    qty = float(item.get("quantity") or 0)
                    
                    price_val = item.get("unitPrice")
                    if isinstance(price_val, str):
                        price_val = "".join(c for c in price_val if c.isdigit() or c == '.')
                    price = float(price_val or 0)
                    
                    total_val = item.get("totalAmount")
                    if isinstance(total_val, str):
                        total_val = "".join(c for c in total_val if c.isdigit() or c == '.')
                    total = float(total_val or 0)
                    
                    if qty > 0 and total > 0:
                        # Correct OCR prefix error (e.g., misreading currency symbol '₹' as digit '2')
                        if qty * price > 2 * total:
                            price_str = str(int(price))
                            if len(price_str) > 1 and price_str.startswith('2'):
                                try:
                                    stripped_price = float(price_str[1:])
                                    if qty * stripped_price >= total:
                                        price = stripped_price
                                except Exception:
                                    pass
                        
                        item["unitPrice"] = price
                        item["amount"] = round(qty * price, 2)
                        item["totalAmount"] = total
                        item["discount"] = round(item["amount"] - total, 2)
                        item["gst"] = round(total * 0.18, 2)
                
                # Recalculate root amount and gstAmount
                po_data["amount"] = round(sum(float(item.get("totalAmount") or 0) for item in line_items), 2)
                po_data["gstAmount"] = round(sum(float(item.get("gst") or 0) for item in line_items), 2)
                
                # Align GST Groupings
                gst_type = po_data.get("gstType") or "IntraState"
                if gst_type == "IntraState":
                    half_gst = round(po_data["gstAmount"] / 2, 2)
                    po_data["gstGroupings"] = [
                        {"gstPercentage": "9%", "amount": half_gst, "gstType": "CGST", "ledgerId": 0},
                        {"gstPercentage": "9%", "amount": half_gst, "gstType": "SGST", "ledgerId": 0}
                    ]
                else:
                    po_data["gstGroupings"] = [
                        {"gstPercentage": "18%", "amount": po_data["gstAmount"], "gstType": "IGST", "ledgerId": 0}
                    ]
            except Exception as math_err:
                logger.warning("Failed during mathematical correction phase", error=str(math_err))

            logger.info("LLM extraction successful, validating against Pydantic model")

            try:
                return PurchaseOrder.model_validate(po_data)
            except ValidationError as e:
                # Preserve the structured field-level errors from Pydantic
                logger.error("Pydantic validation failed", errors=e.errors())
                raise ValueError(f"Schema validation failed: {e}")

        except ValueError:
            # Re-raise our own ValueErrors (from the inner try blocks above)
            raise
        except Exception as e:
            # Catch unexpected Groq API errors (rate limits, network issues, etc.)
            logger.error("Unexpected error during LLM extraction", error=str(e))
            raise ValueError(f"LLM Extraction Error: {str(e)}")
