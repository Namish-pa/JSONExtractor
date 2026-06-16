from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from src.extraction.pymupdf_adapter import PyMuPDFExtractor
from src.llm.providers.groq_extractor import GroqExtractor
from src.application.orchestrators import PurchaseOrderExtractionWorkflow
from dotenv import load_dotenv
import structlog

load_dotenv()
logger = structlog.get_logger()
router = APIRouter()

# In a real application, dependencies should be injected
# via FastAPI Depends(), but this is sufficient for MVP.
extractor = PyMuPDFExtractor()
llm = GroqExtractor()
workflow = PurchaseOrderExtractionWorkflow(extractor, llm)

@router.post("/purchase-order/extract")
async def extract_purchase_order(file: UploadFile = File(...)):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="File must be a PDF")
        
    logger.info("Received PDF for extraction", filename=file.filename)
    
    file_bytes = await file.read()
    
    result = workflow.execute(file_bytes)
    
    if "error" in result:
        # If it's a validation error, we return 422 Unprocessable Entity
        if result["error"] == "validation_failed":
            return JSONResponse(status_code=422, content=result)
        # Otherwise it's an internal processing error
        return JSONResponse(status_code=500, content=result)
        
    return JSONResponse(status_code=200, content=result)
