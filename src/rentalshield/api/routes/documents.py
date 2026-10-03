"""Rental document endpoints."""
import json
import io
import os
from fastapi import APIRouter, UploadFile, File, HTTPException
import pdfplumber
from loguru import logger
import google.generativeai as genai

router = APIRouter()

# Initialize Gemini
GEMINI_API_KEY = os.getenv("ANTHROPIC_API_KEY")  # Using same env var name for backwards compat
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

@router.post("/parse-contract")
async def parse_contract(file: UploadFile = File(...)):
    """Parse rental contract PDF and extract car details using Claude."""
    try:
        logger.info("PDF upload started: {}", file.filename)

        # Read PDF file
        if not file.filename.endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")

        pdf_content = await file.read()
        logger.info("PDF read: {} bytes", len(pdf_content))

        # Extract text from PDF using pdfplumber
        pdf_text = ""
        try:
            with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
                logger.info("PDF opened, pages: {}", len(pdf.pages))
                # Extract from first few pages
                for i, page in enumerate(pdf.pages[:3]):
                    text = page.extract_text()
                    if text:
                        pdf_text += text + "\n"
                        logger.info("Page {}: {} chars extracted", i, len(text))
        except Exception as e:
            logger.error("PDF extraction error: {}", e)
            raise HTTPException(status_code=400, detail=f"Failed to read PDF: {str(e)}")

        logger.info("Total text extracted: {} chars", len(pdf_text))

        if not pdf_text.strip():
            raise HTTPException(status_code=400, detail="Could not extract text from PDF")

        # Parse with Gemini
        prompt = f"""You are a rental car contract parser. Extract car rental details from this contract text. Be accurate!

CONTRACT TEXT:
{pdf_text}

Extract and return ONLY valid JSON (no markdown, no explanations):
{{
  "rental_provider": "rental company name found in contract",
  "make": "car brand/make",
  "model": "car model",
  "year": "year as string",
  "license_plate": "license plate from contract",
  "vin": "VIN or N/A if not found",
  "color": "car color if mentioned",
  "daily_rate": "daily rate if found",
  "total_price": "total price if found",
  "insurance_type": "insurance type if listed",
  "insurance_price": "insurance price if listed",
  "start_date": "start date in YYYY-MM-DD format",
  "end_date": "end date in YYYY-MM-DD format",
  "pickup_location": "where to pick up car",
  "dropoff_location": "where to drop off car",
  "damages": []
}}"""

        logger.info("Calling Gemini API...")
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(prompt)
        response_text = response.text
        logger.info("Gemini response: {}", response_text[:200])

        # Parse JSON
        json_start = response_text.find('{')
        json_end = response_text.rfind('}') + 1

        if json_start == -1 or json_end == 0:
            logger.error("No JSON found in response: {}", response_text)
            raise HTTPException(status_code=400, detail="Claude response invalid")

        extracted_data = json.loads(response_text[json_start:json_end])
        logger.info("Extracted data: {}", extracted_data)

        return {
            "status": "success",
            "data": extracted_data
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Parse error: {}", e)
        raise HTTPException(status_code=500, detail=f"Parse error: {str(e)}")
