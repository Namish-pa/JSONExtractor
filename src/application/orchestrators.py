from src.extraction.interfaces import DocumentExtractor
from src.llm.interfaces import LLMExtractor
from src.domain.purchase_order import PurchaseOrder
from src.validation.business_rules import validate_business_rules
from src.validation.financial_rules import validate_financial_rules
import structlog

logger = structlog.get_logger()

class PurchaseOrderExtractionWorkflow:
    def __init__(self, extractor: DocumentExtractor, llm: LLMExtractor):
        self.extractor = extractor
        self.llm = llm

    def execute(self, pdf_bytes: bytes) -> dict:
        """
        Executes the extraction pipeline:
        1. PDF -> Text
        2. Text -> PO Object (via LLM)
        3. PO Object -> Validation
        """
        logger.info("Starting PO Extraction Workflow")
        
        # 1. Extraction
        try:
            text = self.extractor.extract_text(pdf_bytes)
        except Exception as e:
            logger.error("Extraction stage failed", error=str(e))
            return {"error": "extraction_failed", "details": str(e)}
            
        if not text.strip():
            logger.warning("No text extracted from PDF")
            return {"error": "no_text_found"}
            
        # 2. LLM Processing
        try:
            po: PurchaseOrder = self.llm.extract_purchase_order(text)
        except Exception as e:
            logger.error("LLM extraction stage failed", error=str(e))
            return {"error": "llm_extraction_failed", "details": str(e)}
            
        # 3. Validation
        validation_errors = []
        validation_errors.extend(validate_business_rules(po))
        validation_errors.extend(validate_financial_rules(po))
        
        if validation_errors:
            logger.warning("Validation failed", errors=validation_errors)
            return {
                "error": "validation_failed",
                "details": validation_errors,
                "partial_data": po.model_dump(mode="json")
            }
            
        logger.info("Workflow completed successfully")
        return po.model_dump(mode="json")
