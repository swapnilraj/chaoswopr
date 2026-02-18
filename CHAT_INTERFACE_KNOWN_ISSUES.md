# Chat Interface Known Issues

## Issue 1: LLM API JSON Decode Error (RESOLVED)

**Error:**
```
requests.exceptions.JSONDecodeError: Expecting value: line 153 column 1 (char 836)
```

**Root Cause:**
The OpenRouter API may return an error response (HTML or text) instead of JSON when:
1. API key is missing or invalid
2. Request payload is too large (64 tools = large schema)
3. API rate limits exceeded

**Fix Applied:**
Updated `call_llm_with_tools()` in `streamlit_app.py` to:
- Catch JSON parsing errors
- Show response preview in error message
- Better error handling for unexpected response formats

**Workarounds:**

### 1. Check API Key
Ensure `.env` file has valid key:
```bash
echo $OPENROUTER_API_KEY
```

### 2. Test with Smaller Tool Set (if needed)
If payload is too large, you can temporarily reduce tools:

**Option A:** Comment out some tool imports in `tools/__init__.py`:
```python
# Temporarily disable some categories
# from chaoswopr.chat.tools import observability  # Comment out
# from chaoswopr.chat.tools import analysis       # Comment out
```

**Option B:** Use tool filtering (future enhancement):
```python
def get_tools_for_llm(categories: list[str] = None) -> list[dict]:
    """Get tools filtered by category."""
    # Filter TOOLS_REGISTRY by category
    ...
```

### 3. Check OpenRouter API Status
Visit https://openrouter.ai/status to verify service is operational.

### 4. Try Different Model
Change model in `streamlit_app.py`:
```python
"model": "anthropic/claude-sonnet-3.5",  # Smaller context window
# instead of "anthropic/claude-opus-4"
```

## Issue 2: Streamlit Rerun on Approval (MINOR)

**Description:**
Approval workflows may cause multiple reruns in Streamlit, leading to duplicate API calls.

**Status:** Low priority - Streamlit caching handles this reasonably well.

**Future Fix:** Use `st.session_state` to track approval state and prevent duplicate calls.

## Issue 3: Tool Execution Without Infrastructure (EXPECTED)

**Description:**
Many tools return mock data when infrastructure isn't deployed (e.g., "⚠️ Requires deployed testnet").

**Status:** This is by design - allows testing chat interface without infrastructure.

**To Enable Full Functionality:**
1. Deploy a testnet: `deploy_testnet(256)`
2. Run Prometheus for metrics
3. Run experiments to generate data

## Recommendations

### For Development/Testing:
- Use dry-run mode (default)
- Test with mock tools first
- Verify API key is configured

### For Production:
- Deploy full infrastructure
- Use real API key
- Monitor API rate limits
- Consider caching LLM responses

### Performance Optimization (Future):
- Tool schema compression
- Lazy loading of tool categories
- Response caching
- Streaming for long results

## Success Verification

If chat is working correctly, you should see:
```
✅ OpenRouter API configured (in sidebar)
🟢 Tool execution without errors
📊 All 64 tools available (sidebar shows count)
```

If you see errors:
1. Check `.env` file has `OPENROUTER_API_KEY`
2. Verify API key is valid
3. Check response error message (now shows preview)
4. Try with fewer tools if payload too large

## Getting Help

If issues persist:
1. Check error message (now more detailed)
2. Review `docs/CHAT_INTERFACE.md` troubleshooting section
3. Verify all dependencies installed: `pip install streamlit python-dotenv requests`
4. Check Streamlit version: `streamlit --version` (should be 1.30+)
