from typing import Protocol
from src.domain.purchase_order import PurchaseOrder

class LLMExtractor(Protocol):
    """
    Protocol for extracting structured data from text using an LLM.
    """
    def extract_purchase_order(self, text: str) -> PurchaseOrder:
        ...
