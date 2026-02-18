#!/usr/bin/env python3
"""Verification script for chat interface tools.

Checks that all 64 tools are properly registered and categorized.

Usage:
    python scripts/verify_chat_tools.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from chaoswopr.chat.tools import TOOLS_REGISTRY, SafetyTier


def verify_tools():
    """Verify all tools are registered correctly."""
    print("🔍 Verifying Chat Interface Tools\n")

    # Expected tool counts per category
    expected_counts = {
        "infrastructure": 12,
        "observability": 15,
        "experiment": 16,
        "analysis": 10,
        "safety": 5,
        "agents": 6,
    }

    # Total expected
    total_expected = sum(expected_counts.values())

    # Check total count
    actual_count = len(TOOLS_REGISTRY)
    print(f"📊 Tool Count: {actual_count}/{total_expected}")

    if actual_count != total_expected:
        print(f"❌ FAIL: Expected {total_expected} tools, got {actual_count}")
        return False

    print("✅ PASS: All 64 tools registered\n")

    # Categorize by source module
    by_category = {}
    for tool_name, tool_def in TOOLS_REGISTRY.items():
        # Get category from implementation function
        impl_func = __import__(
            f"chaoswopr.chat.tools.{tool_name}", fromlist=[""]
        ).__name__

        category = None
        for cat in expected_counts.keys():
            if cat in impl_func or cat in tool_name:
                category = cat
                break

        if not category:
            # Guess from tool name
            for cat in expected_counts.keys():
                if cat in tool_name.lower():
                    category = cat
                    break

        if not category:
            category = "unknown"

        if category not in by_category:
            by_category[category] = []
        by_category[category].append(tool_name)

    # Check counts per category
    print("📁 Tools by Category:")
    all_pass = True

    for category, expected in expected_counts.items():
        actual = len(by_category.get(category, []))
        status = "✅" if actual == expected else "❌"

        print(f"  {status} {category.capitalize()}: {actual}/{expected}")

        if actual != expected:
            all_pass = False

    print()

    # Check safety tier distribution
    print("🛡️ Safety Tier Distribution:")
    tier_counts = {}

    for tool_def in TOOLS_REGISTRY.values():
        tier = tool_def["safety_tier"]
        if tier not in tier_counts:
            tier_counts[tier] = 0
        tier_counts[tier] += 1

    for tier in SafetyTier:
        count = tier_counts.get(tier, 0)
        print(f"  - {tier.name} (Tier {tier.value}): {count} tools")

    print()

    # Verify each tool has required fields
    print("🔍 Tool Schema Validation:")
    schema_pass = True

    for tool_name, tool_def in TOOLS_REGISTRY.items():
        required_fields = ["name", "description", "parameters", "safety_tier"]
        missing = [f for f in required_fields if f not in tool_def]

        if missing:
            print(f"  ❌ {tool_name}: Missing fields {missing}")
            schema_pass = False

        # Validate parameters schema
        params = tool_def.get("parameters", {})
        if not isinstance(params, dict):
            print(f"  ❌ {tool_name}: Invalid parameters schema (not a dict)")
            schema_pass = False

        if params.get("type") != "object":
            print(f"  ❌ {tool_name}: Parameters must have type='object'")
            schema_pass = False

    if schema_pass:
        print("  ✅ All tools have valid schemas")
    else:
        print("  ❌ Some tools have invalid schemas")

    print()

    # List all tools
    print(f"📋 All {len(TOOLS_REGISTRY)} Tools:")
    for i, tool_name in enumerate(sorted(TOOLS_REGISTRY.keys()), 1):
        tool_def = TOOLS_REGISTRY[tool_name]
        tier = tool_def["safety_tier"]
        tier_icon = {
            SafetyTier.READ_ONLY: "🟢",
            SafetyTier.DESIGN: "🟡",
            SafetyTier.INFRASTRUCTURE: "🟠",
            SafetyTier.CHAOS: "🔴",
            SafetyTier.SAFETY_OVERRIDE: "⛔",
        }.get(tier, "❓")

        print(f"  {i:2d}. {tier_icon} {tool_name}")

    print()

    # Final verdict
    if all_pass and schema_pass and actual_count == total_expected:
        print("✅ VERIFICATION PASSED")
        print("\nAll 64 tools are properly registered and categorized.")
        return True
    else:
        print("❌ VERIFICATION FAILED")
        print("\nSome tools are missing or misconfigured.")
        return False


if __name__ == "__main__":
    success = verify_tools()
    sys.exit(0 if success else 1)
