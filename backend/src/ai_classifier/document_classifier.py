"""
Document classifier using PydanticAI and Gemini 2.5 Flash for identifying customs document types.
"""
from __future__ import annotations

import os
from typing import Literal
from pydantic import BaseModel, Field
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider


# Document type enum
DocumentType = Literal["entry_print", "air_waybill", "commercial_invoice", "packing_list", "other"]


class DocumentClassificationOutput(BaseModel):
    """Structured output from the document classifier."""
    document_type: DocumentType = Field(
        ..., 
        description="The type of customs document"
    )


# System prompt for document classification
_SYSTEM_PROMPT = """
You are a customs document classification expert specializing in DHL Express shipments.

Your task is to analyze PDF documents and classify them into one of these categories:

1. **entry_print** - Customs entry/declaration form
   - Contains: Entry number, declarant details, line items with HS codes, customs values
   - Keywords: "Entry", "Declaration", "Customs", "Declarant", "HS Code", "Tariff"
   - Usually has tabular data with item descriptions and classifications

2. **air_waybill** - Air Waybill (AWB) document
   - Contains: AWB number, shipper/consignee details, weight, pieces, flight info
   - Keywords: "Air Waybill", "AWB", "Shipper", "Consignee", "Flight", "MAWB", "HAWB"
   - Typically shows tracking and shipping logistics

3. **commercial_invoice** - Commercial Invoice from supplier
   - Contains: Invoice number, supplier/buyer details, line items with prices, totals
   - Keywords: "Commercial Invoice", "Invoice", "Supplier", "Buyer", "Payment Terms", "Total Amount"
   - Shows pricing and payment information

4. **packing_list** - Packing list with item details
   - Contains: Package details, dimensions, weights, item quantities
   - Keywords: "Packing List", "Package", "Carton", "Dimensions", "Gross Weight"
   - Focus on physical packaging information

5. **other** - Any other document type
   - Use this for certificates, licenses, or unrecognizable documents

Based on the document content, classify it into the most appropriate category.

Return JSON with this exact field:
{
  "document_type": one of the 5 types above
}
"""


def _get_document_classifier_agent() -> Agent:
    """Create and return a PydanticAI agent for document classification."""
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY environment variable is required")
    
    model = GoogleModel(
        "gemini-2.5-flash",
        provider=GoogleProvider(api_key=api_key),
    )
    
    return Agent(
        model=model,
        system_prompt=_SYSTEM_PROMPT,
        output_type=DocumentClassificationOutput,
        retries=2,
        model_settings={"temperature": 0.1},  # Low temperature for consistent classification
    )


# Global agent instance (created once)
_classifier_agent: Agent | None = None


def get_classifier_agent() -> Agent:
    """Get or create the classifier agent (singleton pattern)."""
    global _classifier_agent
    if _classifier_agent is None:
        _classifier_agent = _get_document_classifier_agent()
    return _classifier_agent


async def classify_document(pdf_content: bytes, filename: str) -> DocumentClassificationOutput:
    """
    Classify a PDF document into its type.
    
    Args:
        pdf_content: Raw PDF file content as bytes
        filename: Original filename for context
        
    Returns:
        DocumentClassificationOutput with document_type
    """
    agent = get_classifier_agent()
    
    # Build message parts list (text + binary content)
    message_parts = []
    
    # Add text prompt
    prompt = f"""
Analyze this PDF document and classify it.

Filename: {filename}

Determine what type of customs document this is based on the content.

Return the classification in the required JSON format with document_type.
"""
    message_parts.append(prompt)
    
    # Add PDF binary content
    message_parts.append(BinaryContent(
        data=pdf_content,
        media_type="application/pdf"
    ))
    
    # Run the agent with the message parts
    result = await agent.run(message_parts)
    
    return result.output


def get_file_suffix(document_type: str) -> str:
    """
    Get the file suffix for a given document type.
    
    Args:
        document_type: The classified document type
        
    Returns:
        String suffix to append to filename (e.g., "_entry_print")
    """
    return f"_{document_type}"
