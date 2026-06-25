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

CRITICAL RULES for numeric fields:
1. `lineItem.discount` — MUST be an absolute currency amount (e.g. 1750.0), NEVER a percentage (e.g. 5 or 0.05).
2. `lineItem.gst` — MUST be an absolute currency amount of tax charged (e.g. 5985.0), NEVER a rate (e.g. 0.18 or 18).
3. `lineItem.amount` — MUST equal quantity * unitPrice (gross, before discount).
4. `lineItem.totalAmount` — MUST equal amount - discount (post-discount, pre-GST subtotal).
5. Root `amount` — MUST equal the sum of all lineItem.totalAmount values (total pre-GST).
6. Root `gstAmount` — MUST be the total GST in currency; MUST equal sum of gstGroupings amounts.
7. If optional data is missing, set the value to null.
8. Ensure all numeric fields are correctly typed as numbers (not strings).
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
