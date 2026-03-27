# ════════════════════════════════════════════════════════════════
# CS5 COMPLETE TESTING PLAN — March 27, 2026 (Submission Day)
# ════════════════════════════════════════════════════════════════
#
# STATUS:
#   ✅ 17/17 unit tests passing
#   ✅ Docker 8 services running  
#   ✅ MCP server recognized by Claude Desktop (tools + prompts visible)
#   🔧 FIXED: structlog stdout → stderr (was corrupting MCP JSON)
#
# WHAT CHANGED:
#   config.py — structlog now writes to stderr instead of stdout
#   This prevents log messages from corrupting the MCP stdio JSON-RPC channel
#
# ════════════════════════════════════════════════════════════════


# ──────────────────────────────────────────────────────────────
# STEP 1: VERIFY THE FIX — Re-run tests
# ──────────────────────────────────────────────────────────────

# Terminal 1 (cs5 folder):
cd D:\DAMG7245_Big_Data_Systems\BigDataIA-SPring26-Team-4-case-study-5\cs5

uv run python -m pytest tests/ -v

# EXPECTED: All 17 tests pass (same as before)
# The structlog config change shouldn't break any tests.


# ──────────────────────────────────────────────────────────────
# STEP 2: VERIFY DOCKER IS RUNNING
# ──────────────────────────────────────────────────────────────

# Terminal 2 (root folder):
cd D:\DAMG7245_Big_Data_Systems\BigDataIA-SPring26-Team-4-case-study-5

docker compose -f docker/compose.yaml ps

# EXPECTED: 8 services running (api, streamlit, redis, postgres,
# airflow-init, airflow-scheduler, airflow-webserver, etc.)
#
# Quick API check:
# Open browser → http://localhost:8000/docs
# Should see FastAPI Swagger UI


# ──────────────────────────────────────────────────────────────
# STEP 3: RESTART CLAUDE DESKTOP — Fix MCP JSON error
# ──────────────────────────────────────────────────────────────

# 1. Fully QUIT Claude Desktop (right-click tray icon → Quit, not just close)
# 2. Reopen Claude Desktop
# 3. Click the MCP tools icon (hammer + wrench icon, bottom-left of chat input)
# 4. You should see:
#      ✅ pe-orgair-server (enabled, blue toggle ON)
#      No error message about "Unexpected non-whitespace character"
#
# If the error persists:
#   - Open DevTools in Claude Desktop: Ctrl+Shift+I → Console tab
#   - Look for the actual error message
#   - The fix redirects ALL structlog to stderr, so stdout should be clean


# ──────────────────────────────────────────────────────────────
# STEP 4: TEST MCP TOOLS IN CLAUDE DESKTOP
# ──────────────────────────────────────────────────────────────

# IMPORTANT: Docker must be running for these to work!
# Test each of the 6 tools one by one.

# ── Test 1: calculate_org_air_score ──
# Type in Claude Desktop:
#   "Calculate the Org-AI-R score for NVDA"
#
# EXPECTED: Claude calls the MCP tool, returns JSON with:
#   org_air, vr_score, hr_score, synergy_score, dimension_scores, CI
#   All values should be non-zero real numbers from CS3

# ── Test 2: get_company_evidence ──
# Type:
#   "Show me evidence for NVIDIA's talent dimension"
#
# EXPECTED: Returns evidence items with source_type, content, confidence
#   Should include job postings, SEC filings, etc. from CS2

# ── Test 3: generate_justification ──
# Type:
#   "Generate a justification for NVDA's data infrastructure dimension"
#
# EXPECTED: Returns score, level, level_name, evidence_strength,
#   rubric_criteria, supporting_evidence, gaps_identified, summary
#   This calls CS4 RAG — needs the RAG service available

# ── Test 4: project_ebitda_impact ──
# Type:
#   "Project EBITDA impact for NVDA with entry score 45, target 75, HR score 60"
#
# EXPECTED: Returns conservative, base, optimistic scenarios
#   + risk_adjusted percentage + requires_approval flag

# ── Test 5: run_gap_analysis ──
# Type:
#   "Run a gap analysis for JPM with target Org-AI-R of 75"
#
# EXPECTED: Returns gaps by dimension, priority ranking,
#   initiatives, investment estimates, 100-day plan

# ── Test 6: get_portfolio_summary ──
# Type:
#   "Get the portfolio summary for growth_fund_v"
#
# EXPECTED: Returns fund_air, company_count (5), and all 5 companies
#   with their org_air, vr_score, hr_score, sector


# ── Test 7: MCP PROMPTS (the full workflow) ──
# Click the prompt icon (book icon) in Claude Desktop
# You should see:
#   "Due diligence assessment"
#   "Ic meeting prep"
#
# Select "Due diligence assessment" → enter "NVDA"
# Claude will run the full multi-step DD workflow:
#   1. Calculates score
#   2. Reviews evidence for weak dimensions
#   3. Gets justifications
#   4. Runs gap analysis
#   5. Projects EBITDA
#
# OR type the PDF prompt directly:
#   "Claude, prepare the IC meeting for NVIDIA."
# This should trigger the ic_meeting_prep prompt and call multiple tools.

# ── Test 8: MCP RESOURCES ──
# Type:
#   "What are the current Org-AI-R scoring parameters?"
# Claude should read the orgair://parameters/v2.0 resource
#
# Type:
#   "Show me the sector definitions and benchmarks"
# Claude should read the orgair://sectors resource


# ──────────────────────────────────────────────────────────────
# STEP 5: TEST STREAMLIT DASHBOARD
# ──────────────────────────────────────────────────────────────

# Terminal 3:
cd D:\DAMG7245_Big_Data_Systems\BigDataIA-SPring26-Team-4-case-study-5\cs5\src

uv run streamlit run dashboard/app.py

# EXPECTED:
#   Browser opens at http://localhost:8501
#   - Sidebar: "PE Org-AI-R" with Fund ID input (default: growth_fund_v)
#   - Top row: Fund-AI-R metric, Company Count (5), Avg V^R, Avg Delta
#   - VR vs HR scatter plot with threshold lines at 60
#   - Company table with RdYlGn gradient on org_air column
#   - All 5 companies: NVDA, JPM, WMT, GE, DG
#
# If you see "Failed to connect to CS1-CS4" → Docker isn't running


# ──────────────────────────────────────────────────────────────
# STEP 6: VERIFY "NO MOCK DATA" REQUIREMENT
# ──────────────────────────────────────────────────────────────

# This is how the TA will grade. Stop Docker and verify tools error.

# Stop Docker:
docker compose -f docker/compose.yaml down

# Now in Claude Desktop, type:
#   "Calculate the Org-AI-R score for NVDA"
#
# EXPECTED: Should return an ERROR (connection refused), NOT fake data
# This proves your tools call real CS1-CS4, not hardcoded values.

# Streamlit dashboard should also show an error.

# RESTART Docker when done:
docker compose -f docker/compose.yaml up -d


# ──────────────────────────────────────────────────────────────
# STEP 7: TEST AGENTIC DD EXERCISE (Optional — needs OpenAI key)
# ──────────────────────────────────────────────────────────────

# Only if you have OPENAI_API_KEY in src/.env:

cd D:\DAMG7245_Big_Data_Systems\BigDataIA-SPring26-Team-4-case-study-5\cs5\src

uv run python -m exercises.agentic_due_diligence

# EXPECTED:
#   ════════════════════════════════════════════════
#   PE Org-AI-R: Agentic Due Diligence
#   ════════════════════════════════════════════════
#   Running full assessment for NVDA...
#   Org-AI-R Score: XX.X
#   HITL Required: True/False
#   Status: approved / N/A
#   All data came from CS1-CS4 via MCP tools.


# ──────────────────────────────────────────────────────────────
# STEP 8: QUICK SANITY CHECKLIST
# ──────────────────────────────────────────────────────────────

# Before submitting, verify:
#
# ✅ 17/17 unit tests pass (uv run python -m pytest tests/ -v)
# ✅ Docker 8 services healthy (docker compose ... ps)
# ✅ Claude Desktop shows pe-orgair-server (no JSON error)
# ✅ Each of the 6 MCP tools returns real data
# ✅ Prompts appear in Claude Desktop (book icon)
# ✅ Resources work ("what are the scoring parameters?")
# ✅ Streamlit dashboard loads with 5 companies
# ✅ Stopping Docker → MCP tools return errors (no mock data)
# ✅ README.md explains how to run everything


# ──────────────────────────────────────────────────────────────
# TROUBLESHOOTING
# ──────────────────────────────────────────────────────────────

# "MCP pe-orgair-server: Unexpected non-whitespace character after JSON"
#   → This was caused by structlog writing to stdout
#   → FIX: config.py now redirects all structlog to stderr
#   → Fully quit and restart Claude Desktop after the fix

# Claude Desktop shows tools but they all error:
#   → Docker isn't running — start it with docker compose up -d
#   → Check http://localhost:8000/docs loads in browser

# "generate_justification" errors:
#   → CS4 RAG needs the ChromaDB vector store populated
#   → If the RAG index doesn't exist, this tool will error
#   → The other 5 tools should still work fine

# Streamlit: "RuntimeError: This event loop is already running"
#   → nest_asyncio should handle this (check dashboard/app.py imports it)

# Tests fail after config.py change:
#   → Run: uv run python -m pytest tests/ -v --tb=short
#   → If it's an import error, check structlog version: uv run pip show structlog
