# Document Intelligence Pipeline MVP

This project is a Document Intelligence Pipeline that extracts structured JSON data from Purchase Order (PO) and Purchase Invoice PDFs using OCR, LLMs, and Pydantic validation.

---

## How It Works

The extraction pipeline processes documents in four stages:

1. **Ingestion & Primary Extraction**:
   - The PDF is parsed page-by-page using **PyMuPDF (fitz)**.
   - If the page has an embedded text layer (native digital PDF), the text is extracted directly.
2. **OCR Fallback (Tesseract)**:
   - If a page has no embedded text (scanned document or image-only PDF), the pipeline renders the page to a high-resolution PNG and runs **Tesseract OCR** via `pytesseract` to extract the text.
3. **Mathematical Self-Consistency & OCR Error Correction**:
   - The OCR text is passed to **Groq (`llama-3.3-70b-versatile`)** to extract JSON matching the schema.
   - Because OCR frequently misreads the Rupee symbol (`₹`) as the digit `2` (e.g. reading `₹ 1,500.00` as `21,500.00`), a Python post-processing utility automatically detects these errors, cleans the unit prices, and recalculates the line items (`amount`, `discount`, `gst`) and root totals deterministically to guarantee mathematical consistency.
4. **Validation**:
   - The parsed document is validated against **Pydantic schema constraints** along with strict domain business and financial rule checkers.

---

## Installation

### 1. Prerequisites (Tesseract OCR)
Tesseract must be installed on your system:
- **Windows**: Download and run the Tesseract installer.
- Ensure Tesseract is installed to the default location: `C:\Program Files\Tesseract-OCR\tesseract.exe`. The pipeline checks this path automatically.

### 2. Setup Python Virtual Environment
Clone this repository, then create and activate the virtual environment:
```powershell
# Create venv
python -m venv .venv

# Activate venv
.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Variables
Create a `.env` file in the root directory and add your Groq API key:
```ini
GROQ_API_KEY=your_groq_api_key_here
```

---

## Running the Application

Start the FastAPI application with reload enabled:
```powershell
.venv\Scripts\uvicorn main:app --reload
```
Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) in your browser to access the frontend web interface, where you can upload invoice PDFs, trigger extraction, and copy the output JSON.

---

## Running Tests

Run the test suite using `pytest`:
```powershell
.venv\Scripts\pytest
```
