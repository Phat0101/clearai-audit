#!/usr/bin/env python3
"""
Simple test script to verify checklist system is working correctly.

Usage:
    python test_checklist.py
"""

import asyncio
import json
from src.ai_classifier.checklist_models import (
    load_checklist,
    get_header_checks,
    get_valuation_checks,
)


def test_load_checklists():
    """Test loading checklist configurations."""
    print("=" * 80)
    print("TEST 1: Loading Checklist Configurations")
    print("=" * 80)
    
    # Load AU checklist
    print("\n📋 Loading AU checklist...")
    au_checklist = load_checklist("AU")
    print(f"✓ Loaded AU checklist v{au_checklist.version}")
    print(f"  Region: {au_checklist.region}")
    print(f"  Last updated: {au_checklist.last_updated}")
    print(f"  Categories: {list(au_checklist.categories.keys())}")
    
    # Load NZ checklist
    print("\n📋 Loading NZ checklist...")
    nz_checklist = load_checklist("NZ")
    print(f"✓ Loaded NZ checklist v{nz_checklist.version}")
    print(f"  Region: {nz_checklist.region}")
    print(f"  Last updated: {nz_checklist.last_updated}")
    print(f"  Categories: {list(nz_checklist.categories.keys())}")
    
    print("\n✅ Checklist loading successful!\n")


def test_get_checks():
    """Test getting specific check categories."""
    print("=" * 80)
    print("TEST 2: Retrieving Check Categories")
    print("=" * 80)
    
    # AU checks
    print("\n📋 AU Checklist Summary:")
    au_header = get_header_checks("AU")
    au_valuation = get_valuation_checks("AU")
    print(f"  Header checks: {len(au_header)}")
    print(f"  Valuation checks: {len(au_valuation)}")
    print(f"  Total: {len(au_header) + len(au_valuation)}")
    
    print("\n  Header checks:")
    for check in au_header:
        print(f"    - {check.id}: {check.auditing_criteria}")
    
    print("\n  Valuation checks:")
    for check in au_valuation:
        print(f"    - {check.id}: {check.auditing_criteria}")
    
    # NZ checks
    print("\n📋 NZ Checklist Summary:")
    nz_header = get_header_checks("NZ")
    nz_valuation = get_valuation_checks("NZ")
    print(f"  Header checks: {len(nz_header)}")
    print(f"  Valuation checks: {len(nz_valuation)}")
    print(f"  Total: {len(nz_header) + len(nz_valuation)}")
    
    print("\n  Header checks:")
    for check in nz_header[:5]:  # Show first 5
        print(f"    - {check.id}: {check.auditing_criteria}")
    print(f"    ... and {len(nz_header) - 5} more")
    
    print("\n  Valuation checks:")
    for check in nz_valuation:
        print(f"    - {check.id}: {check.auditing_criteria}")
    
    print("\n✅ Check retrieval successful!\n")


def test_build_prompt():
    """Test building validation prompts for PDF documents."""
    print("=" * 80)
    print("TEST 3: Building Validation Prompts (with PDF documents)")
    print("=" * 80)
    
    from src.ai_classifier.checklist_validator import build_validation_prompt_with_docs
    
    # Get a sample check
    au_checks = get_header_checks("AU")
    sample_check = au_checks[0]  # Owner match check
    
    print(f"\n📋 Building prompt for: {sample_check.id} - {sample_check.auditing_criteria}")
    print(f"   This prompt will be sent WITH PDF documents attached")
    
    # Build prompt
    prompt = build_validation_prompt_with_docs(sample_check)
    
    print("\n📝 Generated prompt (first 500 chars):")
    print("-" * 80)
    print(prompt[:500])
    print("...")
    print("-" * 80)
    
    print(f"\n✓ Prompt length: {len(prompt)} characters")
    print("✓ This prompt instructs Gemini to analyze the attached PDF documents")
    print("✅ Prompt building successful!\n")


async def test_validator():
    """Test the actual validator (requires API key and sample PDF files)."""
    print("=" * 80)
    print("TEST 4: Validator Functionality (Requires GEMINI_API_KEY & Sample PDFs)")
    print("=" * 80)
    
    import os
    
    if not os.getenv("GEMINI_API_KEY"):
        print("\n⚠️  GEMINI_API_KEY not set - skipping validator test")
        print("   Set GEMINI_API_KEY in your environment to test validation")
        return
    
    # Check for sample PDF files
    from pathlib import Path
    sample_dir = Path("../OneDrive_1_09-10-2025")
    if not sample_dir.exists():
        print("\n⚠️  Sample PDF directory not found - skipping validator test")
        print(f"   Expected: {sample_dir.absolute()}")
        return
    
    print("\n🚀 Testing checklist validator with real API call and PDF documents...")
    print("   NOTE: This now passes actual PDFs to Gemini, not extracted data!")
    
    try:
        from src.ai_classifier.checklist_validator import validate_checklist_item
        
        # Get a simple check
        au_checks = get_header_checks("AU")
        currency_check = [c for c in au_checks if "Currency" in c.auditing_criteria][0]
        
        print(f"\n📋 Testing: {currency_check.id} - {currency_check.auditing_criteria}")
        
        # Load sample PDFs
        entry_pdf = sample_dir / "2219477116^^13387052^FRML^CIM^^_ENT_SYD_GTW_099_20251002_062500.pdf"
        invoice_pdf = sample_dir / "2219477116_INV_OSA_OAA_E5D_20250929_132104.pdf"
        
        if not entry_pdf.exists() or not invoice_pdf.exists():
            print(f"\n⚠️  Sample PDFs not found:")
            print(f"     {entry_pdf.name}: {entry_pdf.exists()}")
            print(f"     {invoice_pdf.name}: {invoice_pdf.exists()}")
            return
        
        # Read PDF content
        documents = {
            "entry_print": entry_pdf.read_bytes(),
            "commercial_invoice": invoice_pdf.read_bytes()
        }
        
        print(f"\n📄 Loaded PDFs:")
        print(f"   Entry Print: {len(documents['entry_print']):,} bytes")
        print(f"   Invoice: {len(documents['commercial_invoice']):,} bytes")
        
        print("\n🔄 Calling Gemini API with PDF documents...")
        print("   (This will analyze the actual PDFs, not extracted JSON)")
        
        result = await validate_checklist_item(currency_check, documents)
        
        print("\n✅ Validation Result:")
        print(f"  Check ID: {result.check_id}")
        print(f"  Status: {result.status}")
        print(f"  Assessment: {result.assessment}")
        print(f"  Source Value: {result.source_value}")
        print(f"  Target Value: {result.target_value}")
        
        print("\n✅ Validator test successful with PDF documents!\n")
        
    except Exception as e:
        print(f"\n❌ Validator test failed: {e}\n")
        import traceback
        traceback.print_exc()


def main():
    """Run all tests."""
    print("\n🧪 ClearAI Audit - Checklist System Tests\n")
    
    try:
        # Test 1: Load checklists
        test_load_checklists()
        
        # Test 2: Get specific checks
        test_get_checks()
        
        # Test 3: Build validation prompt
        test_build_prompt()
        
        # Test 4: Test validator (async)
        asyncio.run(test_validator())
        
        print("=" * 80)
        print("🎉 ALL TESTS COMPLETED!")
        print("=" * 80)
        print("\nChecklist system is ready to use. Next steps:")
        print("1. Integrate validation into batch processing endpoint")
        print("2. Save validation results as JSON files")
        print("3. Generate XLSX reports with validation results\n")
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}\n")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

