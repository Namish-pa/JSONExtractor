import json
import os
from groq import Groq
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
  "date": "string (required, ISO-8601 date: YYYY-MM-DD)",
  "status": "string (required)",
  "partyLedgerId": "integer (required, output integer)",
  "purchaseLedgerId": "integer (required, output integer)",
  "partyAddress": "string (optional)",
  "billingAddress": "string (optional)",
  "billingState": "string (optional)",
  "shippingAddress": "string (optional)",
  "shippingState": "string (optional)",
  "gstType": "string (required)",
  "grnIds": ["integer"],
  "storeIds": ["integer"],
  "awsFileId": "string (optional)",
  "amount": "float (required)",
  "gstAmount": "float (required)",
  "gstGroupings": [
    {
      "gstPercentage": "string (required)",
      "amount": "float (required)",
      "gstType": "string (required)",
      "ledgerId": "integer (required)"
    }
  ],
  "lineItems": [
    {
      "productId": "integer (required)",
      "productName": "string (required)",
      "description": "string (optional)",
      "hsnCode": "string (optional)",
      "unitType": "string (optional)",
      "quantity": "float (required)",
      "discount": "float (required)",
      "unitPrice": "float (required)",
      "amount": "float (required)",
      "gst": "float (required)",
      "totalAmount": "float (required)",
      "grnId": "integer (optional)",
      "storeId": "integer (optional)",
      "typeOfService": "string (required)"
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

If optional data is missing, set the value to null.
Ensure all numeric fields are correctly typed as numbers (not strings).
"""

class GroqExtractor(LLMExtractor):
    def __init__(self, api_key: str = None, model: str = "llama3-70b-8192"):
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
            # Parse the JSON string into our Pydantic model for schema enforcement
            po_data = json.loads(raw_json_str)
            
            logger.info("LLM extraction successful, validating against Pydantic model")
            return PurchaseOrder.model_validate(po_data)
            
        except Exception as e:
            logger.error("Failed during LLM extraction or parsing", error=str(e))
            raise ValueError(f"LLM Extraction Error: {str(e)}")
