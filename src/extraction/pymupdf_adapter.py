import fitz  # PyMuPDF
from src.extraction.interfaces import DocumentExtractor

class PyMuPDFExtractor(DocumentExtractor):
    """
    Extracts text from PDF files using PyMuPDF (fitz).
    """
    def extract_text(self, file_bytes: bytes) -> str:
        text_content = []
        try:
            # Open the PDF from bytes
            with fitz.open(stream=file_bytes, filetype="pdf") as doc:
                for page_num in range(len(doc)):
                    page = doc.load_page(page_num)
                    # Extract text preserving basic block structure
                    text = page.get_text("text")
                    text_content.append(text)
            
            return "\n\n".join(text_content)
        except Exception as e:
            raise ValueError(f"Failed to extract text from PDF: {str(e)}")
