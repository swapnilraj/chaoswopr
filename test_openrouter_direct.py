#!/usr/bin/env python3
"""Direct test of OpenRouter API integration."""

import os
import sys
from pathlib import Path

# Add source to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

# Load .env
from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from chaoswopr.agents.openrouter_client import OpenRouterLLMClient
from config.llm_schemas import HYPOTHESIS_SCHEMA, HYPOTHESIS_SYSTEM_PROMPT


def main():
    """Test OpenRouter API directly."""
    print("=" * 70)
    print("Direct OpenRouter API Test")
    print("=" * 70)
    print()

    # Get API key
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        print("❌ OPENROUTER_API_KEY not found in environment")
        sys.exit(1)

    print(f"API Key: {api_key[:20]}...")
    print()

    # Create client
    print("Creating OpenRouter client...")
    client = OpenRouterLLMClient(
        api_key=api_key,
        model="anthropic/claude-opus-4",
        timeout_seconds=60,
        max_retries=3,
    )
    print(f"✅ Client created")
    print(f"   Available: {client.is_available()}")
    print()

    # Test simple generation
    print("Test 1: Simple text generation")
    print("-" * 70)
    try:
        response = client.generate(
            prompt="What is the capital of France? Answer in one word.",
            temperature=0.3,
            max_tokens=100,
        )
        print(f"Response: {response.content}")
        print(f"Model: {response.model}")
        print(f"Success: {response.success}")
        if response.usage:
            print(f"Tokens: {response.usage}")
        print("✅ Simple generation successful")
    except Exception as e:
        print(f"❌ Simple generation failed: {e}")
        import traceback
        traceback.print_exc()
    print()

    # Test structured JSON generation
    print("Test 2: Structured JSON generation (Ethereum hypothesis)")
    print("-" * 70)

    prompt = """Generate a hypothesis for this Ethereum chaos engineering scenario:

Scenario: Attestation Withholding Attack
- 28% of validators will withhold their attestations
- Duration: 10 minutes
- Network: Ethereum PoS testnet with 384 validators

Generate a detailed hypothesis about what will happen to network finality,
participation rate, and validator behavior during this attack."""

    try:
        response = client.generate(
            prompt=prompt,
            system_prompt=HYPOTHESIS_SYSTEM_PROMPT,
            json_schema=HYPOTHESIS_SCHEMA,
            temperature=0.7,
            max_tokens=2000,
        )

        print(f"Success: {response.success}")
        print(f"Raw response (first 500 chars):")
        print(response.content[:500])
        print("...")
        print()

        print(f"Structured output:")
        import json
        print(json.dumps(response.structured, indent=2))
        print()

        print(f"Model: {response.model}")
        if response.usage:
            print(f"Tokens: {response.usage}")
        print("✅ Structured generation successful")

        # Check if output matches schema
        if response.structured:
            hyp = response.structured
            print()
            print("Hypothesis Details:")
            print(f"  Prediction: {hyp.get('prediction', 'N/A')[:100]}...")
            print(f"  Blast Radius: {hyp.get('blast_radius_percent', 'N/A')}%")
            print(f"  Confidence: {hyp.get('confidence', 'N/A')}")

    except Exception as e:
        print(f"❌ Structured generation failed: {e}")
        import traceback
        traceback.print_exc()
    print()

    # Show stats
    print("=" * 70)
    print("Client Statistics:")
    print(f"  Total calls: {client._total_calls}")
    print(f"  Total tokens: {client._total_tokens}")
    print(f"  Total errors: {client._total_errors}")
    print("=" * 70)


if __name__ == "__main__":
    main()
