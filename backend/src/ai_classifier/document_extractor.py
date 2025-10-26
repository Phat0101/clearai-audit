"""
Document data extraction using PydanticAI and Gemini 2.5 Flash.
Extracts structured data from classified customs documents.
"""
from __future__ import annotations

import os
from typing import List, Optional
from pydantic import BaseModel, Field
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.models.gemini import GeminiModel
from pydantic_ai.providers.google_gla import GoogleGLAProvider


# ============================================================================
# PYDANTIC MODELS (Based on audit-v2 schemas.ts)
# ============================================================================

# Entry Print Schema
class EntryPrintLineItem(BaseModel):
    """Line item in customs entry print."""
    lineNo: int = Field(..., description="Line item number")
    tariff: str = Field(..., description="Tariff code (8 digits)")
    stat: str = Field(..., description="2 digit statistical code")
    quantity: float = Field(..., description="Quantity of the line item")
    quantityUnit: str = Field(..., description="Quantity unit (PC, KG, EA, M)")
    trt: str = Field(..., description="Tariff treatment code after slash in ORIGIN/PREF")
    originPref: str = Field(..., description="Country of origin code before slash")
    invoicePrice: float = Field(..., description="Invoice price from INVOICE PRICE column")
    customsValue: float = Field(..., description="Customs value from CUSTOMS VALUE column")
    dutyRate: float = Field(..., description="Duty rate in percentage")
    duty: float = Field(..., description="Computed duty amount")
    gst: float = Field(..., description="Computed GST amount")
    addInfo: str = Field(..., description="Content from ADD INFO column")
    description: str = Field(..., description="Item description")
    tAndI: float = Field(..., description="Transport & Insurance for this item")
    wet: float = Field(..., description="Wine Equalization Tax")
    voti: float = Field(..., description="Value of taxable importation")
    instrumentNo: Optional[str] = Field(None, description="Instrument reference number")


class EntryPrintExtraction(BaseModel):
    """Structured data extracted from Customs Entry Print."""
    # Header information
    preparedDateTime: str = Field(..., description="Date/time entry prepared")
    jobNo: str = Field(..., description="Job number")
    entryNo: str = Field(..., description="Entry number")
    destinationPort: str = Field(..., description="Destination port code")
    
    # Owner details
    ownerName: str = Field(..., description="Owner name (null if empty)")
    ownerCode: str = Field(..., description="Owner codes (null if empty)")
    
    # Supplier details
    supplierName: str = Field(..., description="Supplier full name")
    supplierCode: str = Field(..., description="Supplier code")
    
    # Agency and transport
    agency: str = Field(..., description="Agency name")
    mode: str = Field(..., description="Mode of transport")
    aRef: str = Field(..., description="A/Ref number")
    aircr: str = Field(..., description="Aircraft code or flight")
    loadPt: str = Field(..., description="Loading port")
    firstPt: str = Field(..., description="First arrival port and date")
    dschPt: str = Field(..., description="Discharge port and date")
    
    # Monetary references
    iTerms: str = Field(..., description="Incoterms (3-letter code)")
    oRef: str = Field(..., description="Original reference")
    fob: float = Field(..., description="FOB in foreign currency")
    fobAUD: float = Field(..., description="FOB in AUD")
    cif: float = Field(..., description="CIF in foreign currency")
    cifAUD: float = Field(..., description="CIF in AUD")
    grwtKg: float = Field(..., description="Gross weight in kg")
    tAndI: float = Field(..., description="Transport & Insurance cost")
    itot: float = Field(..., description="ITOT in foreign currency")
    itotAUD: float = Field(..., description="ITOT in AUD")
    
    # Additional valuations
    totalCustomsValueAUD: float = Field(..., description="Total customs value in AUD")
    factor: float = Field(..., description="Currency factor")
    valuationDate: str = Field(..., description="Valuation date")
    crncys: str = Field(..., description="3-letter currency code")
    calculationDate: str = Field(..., description="Calculation date/time")
    currencyConversionRate: float = Field(..., description="Exchange rate")
    
    # Line items
    lineItems: List[EntryPrintLineItem] = Field(..., description="Array of line items")
    
    # Package/Bill info
    totalNumberOfPackages: int = Field(..., description="Total package count")
    billNos: List[str] = Field(..., description="List of bill numbers")
    
    # Totals
    totalDuty: float = Field(..., description="Total duty")
    totalGST: float = Field(..., description="Total GST")
    totalWET: float = Field(..., description="Total WET")
    otherCharges: float = Field(..., description="Other charges")
    totalAmtPayable: float = Field(..., description="Total amount payable")


# Air Waybill Schema
class AirWaybillExtraction(BaseModel):
    """Structured data extracted from Air Waybill."""
    note: str = Field(..., description="Instructional note")
    date: str = Field(..., description="Date in ISO format")
    awb_number: str = Field(..., description="Air Waybill number")
    courier_service: str = Field(..., description="Courier service name")
    
    # Shipper details
    shipper_company: str = Field(..., description="Shipper company name")
    shipper_contact_person: str = Field(..., description="Shipper contact person")
    shipper_street: str = Field(..., description="Shipper street address")
    shipper_city: str = Field(..., description="Shipper city")
    shipper_state: str = Field(..., description="Shipper state/region")
    shipper_postal_code: str = Field(..., description="Shipper postal code")
    shipper_country: str = Field(..., description="Shipper country")
    shipper_contact_number: str = Field(..., description="Shipper phone")
    
    # Receiver details
    receiver_company: str = Field(..., description="Receiver company name")
    receiver_contact_person: str = Field(..., description="Receiver contact person")
    receiver_street: str = Field(..., description="Receiver street address")
    receiver_city: str = Field(..., description="Receiver city")
    receiver_state: str = Field(..., description="Receiver state/region")
    receiver_postal_code: str = Field(..., description="Receiver postal code")
    receiver_country: str = Field(..., description="Receiver country")
    receiver_contact_number: str = Field(..., description="Receiver phone")
    receiver_email: str = Field(..., description="Receiver email")
    
    # Shipment details
    shipment_reference_number: str = Field(..., description="Shipment reference")
    shipment_customs_value: float = Field(..., description="Declared customs value")
    shipment_currency: str = Field(..., description="Currency code")
    shipment_export_information: str = Field(..., description="Export information")
    shipment_declared_weight_lbs: float = Field(..., description="Weight in pounds")
    shipment_pieces: int = Field(..., description="Number of pieces")
    shipment_contents: str = Field(..., description="Contents description")
    shipment_license_plates_of_pieces: str = Field(..., description="License plates")
    
    # Accounts and routing
    freight_account_number: str = Field(..., description="Freight account number")
    duty_account_number: str = Field(..., description="Duty account number")
    taxes_account_number: str = Field(..., description="Taxes account number")
    duty_tax_status: str = Field(..., description="Duty tax status")
    routing_origin: str = Field(..., description="Routing origin code")
    routing_destination: str = Field(..., description="Routing destination code")
    routing_service_code: str = Field(..., description="Service code")


# Commercial Invoice Schema
class InvoiceLineItem(BaseModel):
    """Line item in commercial invoice."""
    item_number: int = Field(..., description="Line item sequence")
    material_number: str = Field(..., description="Product/part code (not HS code)")
    invoice_tariff_code: str = Field(..., description="Tariff code (null if empty)")
    description: str = Field(..., description="Product description")
    quantity: float = Field(..., description="Quantity")
    quantity_unit: str = Field(..., description="Unit of measure (PC, EA, KG)")
    net_weight: Optional[float] = Field(None, description="Net weight if provided")
    net_weight_unit: Optional[str] = Field(None, description="Weight unit")
    total_price: float = Field(..., description="Line item total price")
    unit_price: float = Field(..., description="Price per unit")
    country_of_origin: str = Field(..., description="Country of origin")


class CommercialInvoiceExtraction(BaseModel):
    """Structured data extracted from Commercial Invoice."""
    invoice_number: str = Field(..., description="Invoice number")
    invoice_date: str = Field(..., description="Invoice date (YYYY-MM-DD)")
    invoice_currency: str = Field(..., description="Currency code")
    supplier_company_name: str = Field(..., description="Supplier company (foreign entity)")
    supplier_address_line1: str = Field(..., description="Supplier address")
    buyer_company_name: str = Field(..., description="Buyer company name")
    buyer_address_line1: str = Field(..., description="Buyer address")
    inco_terms: str = Field(..., description="Incoterms (3-letter code)")
    invoice_total_amount: float = Field(..., description="Total invoice amount")
    international_freight: Optional[float] = Field(None, description="International freight")
    insurance_charges: Optional[float] = Field(None, description="Insurance charges")
    destination_charges: Optional[float] = Field(None, description="Destination charges")
    import_duties: Optional[float] = Field(None, description="Import duties")
    inland_transportation: Optional[float] = Field(None, description="Inland transportation")
    other_charges: Optional[float] = Field(None, description="Other charges")
    fob_amount: Optional[float] = Field(None, description="FOB value (null if not listed)")
    cif_amount: Optional[float] = Field(None, description="CIF value (null if not listed)")
    transport_and_insurance: Optional[float] = Field(None, description="Total transport + insurance")
    invoice_items: List[InvoiceLineItem] = Field(..., description="Array of line items")


# ============================================================================
# AGENT INITIALIZATION AND EXTRACTION FUNCTIONS
# ============================================================================

def _get_extraction_agent(document_type: str, output_model: type[BaseModel]) -> Agent:
    """
    Create a reusable PydanticAI agent for document extraction.
    
    Args:
        document_type: Type of document being extracted
        output_model: Pydantic model for structured output
        
    Returns:
        Configured Agent instance
    """
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY environment variable is required")
    
    model = GeminiModel(
        "gemini-2.5-flash",
        provider=GoogleGLAProvider(api_key=api_key),
    )
    
    # System prompts for each document type
    system_prompts = {
        "entry_print": """You are an expert at extracting structured data from Australian Customs Entry Print documents.

Extract all fields accurately from the document following the schema provided.
Pay special attention to:
- Line items with tariff codes, quantities, and values
- Monetary values in both foreign currency and AUD
- Owner vs Supplier details (they are different)
- INVOICE PRICE vs CUSTOMS VALUE columns (extract from correct column)
- Origin/Pref codes: extract country code before slash, treatment code after slash

Return valid JSON matching the exact schema structure.""",

        "air_waybill": """You are an expert at extracting structured data from Air Waybill documents.

Extract all fields accurately from the document following the schema provided.
Pay special attention to:
- Complete shipper and receiver address details
- AWB number format
- Shipment weight, pieces, and value
- Account numbers for freight, duty, and taxes
- Routing information

Return valid JSON matching the exact schema structure.""",

        "commercial_invoice": """You are an expert at extracting structured data from Commercial Invoice documents.

Extract all fields accurately from the document following the schema provided.
Pay special attention to:
- Supplier is NEVER the Australian entity - always foreign
- Incoterms should be 3-letter code (FOB, CIF, DDP, etc)
- Material number is NOT the HS/tariff code
- FOB amount is 'net value of goods', NOT invoice total
- Line items with quantities, prices, and country of origin

Return valid JSON matching the exact schema structure."""
    }
    
    system_prompt = system_prompts.get(document_type, "Extract structured data from the document.")
    
    return Agent(
        model=model,
        system_prompt=system_prompt,
        output_type=output_model,
        retries=2,
        model_settings={"temperature": 0.1},  # Low temperature for accurate extraction
    )


async def extract_entry_print(pdf_content: bytes, filename: str) -> EntryPrintExtraction:
    """Extract structured data from Entry Print document."""
    agent = _get_extraction_agent("entry_print", EntryPrintExtraction)
    
    message_parts = [
        f"Extract all data from this Customs Entry Print document: {filename}",
        BinaryContent(data=pdf_content, media_type="application/pdf")
    ]
    
    result = await agent.run(message_parts)
    return result.output


async def extract_air_waybill(pdf_content: bytes, filename: str) -> AirWaybillExtraction:
    """Extract structured data from Air Waybill document."""
    agent = _get_extraction_agent("air_waybill", AirWaybillExtraction)
    
    message_parts = [
        f"Extract all data from this Air Waybill document: {filename}",
        BinaryContent(data=pdf_content, media_type="application/pdf")
    ]
    
    result = await agent.run(message_parts)
    return result.output


async def extract_commercial_invoice(pdf_content: bytes, filename: str) -> CommercialInvoiceExtraction:
    """Extract structured data from Commercial Invoice document."""
    agent = _get_extraction_agent("commercial_invoice", CommercialInvoiceExtraction)
    
    message_parts = [
        f"Extract all data from this Commercial Invoice document: {filename}",
        BinaryContent(data=pdf_content, media_type="application/pdf")
    ]
    
    result = await agent.run(message_parts)
    return result.output


# Main extraction router function
async def extract_document_data(
    pdf_content: bytes, 
    filename: str, 
    document_type: str
) -> BaseModel:
    """
    Extract structured data from a document based on its type.
    
    Args:
        pdf_content: Raw PDF file content
        filename: Original filename
        document_type: Type of document (entry_print, air_waybill, commercial_invoice)
        
    Returns:
        Extracted data as appropriate Pydantic model
        
    Raises:
        ValueError: If document type is not supported for extraction
    """
    if document_type == "entry_print":
        return await extract_entry_print(pdf_content, filename)
    elif document_type == "air_waybill":
        return await extract_air_waybill(pdf_content, filename)
    elif document_type == "commercial_invoice":
        return await extract_commercial_invoice(pdf_content, filename)
    else:
        raise ValueError(f"Extraction not supported for document type: {document_type}")

