# ════════════════════════════════════════════════════════════════
# CS5 Testing & Running Guide — Complete Step-by-Step
# ════════════════════════════════════════════════════════════════
#
# Your setup:
#   - VS Code with PowerShell terminal
#   - cs5/ uses uv (NOT Poetry) — Seamus set it up this way
#   - CS1-CS4 Docker services on port 8000
#   - Claude Desktop for MCP testing
#   - Acer Nitro 5, Windows, Python 3.11+
#
# You'll need 3 terminals total:
#   Terminal 1: Docker (CS1-CS4 backend)
#   Terminal 2: Unit tests + MCP server
#   Terminal 3: Streamlit dashboard
#
# ════════════════════════════════════════════════════════════════


# ──────────────────────────────────────────────────────────────
# PHASE 1: Install Dependencies (ONE TIME)
# ──────────────────────────────────────────────────────────────

# Open VS Code → Terminal → PowerShell

# Step 1: Navigate to cs5 folder
cd D:\DAMG7245_Big_Data_Systems\BigDataIA-SPring26-Team-4-case-study-5\cs5

# Step 2: Create virtual environment and install ALL dependencies
uv sync --all-extras
# This reads pyproject.toml, creates .venv/, installs everything
# including dev deps (pytest) and bonus deps (mem0ai)

# Step 3: Verify installation
uv run python -c "import mcp; import langgraph; import streamlit; print('All CS5 deps OK')"

# Step 4: Copy .env.example to .env and fill in your keys
copy src\.env.example src\.env
# Then edit src\.env in VS Code — add your OPENAI_API_KEY and ANTHROPIC_API_KEY


# ──────────────────────────────────────────────────────────────
# PHASE 2: Start CS1-CS4 Backend (Terminal 1)
# ──────────────────────────────────────────────────────────────

# Split terminal in VS Code (Ctrl+Shift+5) → this is Terminal 1

cd D:\DAMG7245_Big_Data_Systems\BigDataIA-SPring26-Team-4-case-study-5
docker compose -f docker/compose.yaml up -d

# Wait for services to be ready (~30 seconds)
# Verify: open http://localhost:8000/docs in browser
# You should see the FastAPI Swagger UI with all endpoints


# ──────────────────────────────────────────────────────────────
# PHASE 3: Run Unit Tests (Terminal 2)
# ──────────────────────────────────────────────────────────────

# Stay in Terminal 2 (or split again)

cd D:\DAMG7245_Big_Data_Systems\BigDataIA-SPring26-Team-4-case-study-5\cs5

# Run ALL tests (these use mocks, don't need Docker running)
uv run python -m pytest tests/ -v

# Expected: 15 tests should pass
# These test:
#   - MCP tools call real CS clients (via mocks)
#   - No hardcoded data (errors when CS is down)
#   - HITL triggers correctly
#   - EBITDA calculator math
#   - Fund-AI-R calculator
#   - Gap analyzer
#   - Supervisor routing logic


# ──────────────────────────────────────────────────────────────
# PHASE 4: Test MCP Server in Claude Desktop
# ──────────────────────────────────────────────────────────────

# IMPORTANT: This tests the MCP server with Claude as the client!
#
# Step 1: Update Claude Desktop config
# The config file is at:
#   C:\Users\deep2\AppData\Roaming\Claude\claude_desktop_config.json
#
# Replace its contents with the config shown below (I'll create it)
#
# Step 2: Restart Claude Desktop (close and reopen the app)
#
# Step 3: In Claude Desktop, you should see "pe-orgair-server" 
#         listed as an MCP server with 6 tools
#
# Step 4: Test by typing in Claude Desktop:
#   "Calculate the Org-AI-R score for NVDA"
#   "Show me evidence for NVIDIA's data infrastructure"
#   "Run a gap analysis for JPM with target 75"
#   "Get the portfolio summary"
#
# NOTE: Docker must be running (Phase 2) for these to work!


# ──────────────────────────────────────────────────────────────
# PHASE 5: Test Streamlit Dashboard (Terminal 3)
# ──────────────────────────────────────────────────────────────

# Split terminal again (Ctrl+Shift+5) → Terminal 3

cd D:\DAMG7245_Big_Data_Systems\BigDataIA-SPring26-Team-4-case-study-5\cs5\src

uv run streamlit run dashboard/app.py

# Opens browser at http://localhost:8501
# You should see:
#   - Fund-AI-R metric
#   - 5 companies loaded from CS1-CS4
#   - V^R vs H^R scatter plot
#   - Company table with color-coded Org-AI-R
#   - Sector distribution charts
#
# NOTE: Docker must be running (Phase 2) for this to work!


# ──────────────────────────────────────────────────────────────
# PHASE 6: Test MCP Server Standalone (Terminal 2)
# ──────────────────────────────────────────────────────────────

# If you want to test the MCP server outside Claude Desktop:

cd D:\DAMG7245_Big_Data_Systems\BigDataIA-SPring26-Team-4-case-study-5\cs5\src

# Run MCP server (stdio transport — for Claude Desktop)
uv run python -m mcp_server.server

# Or test with MCP Inspector (if installed):
# uv run mcp dev mcp_server/server.py


# ──────────────────────────────────────────────────────────────
# PHASE 7: Test Agentic DD Exercise (Terminal 2)
# ──────────────────────────────────────────────────────────────

# This requires:
#   - Docker running (CS1-CS4)
#   - MCP server running (or agents call CS clients directly)
#   - OPENAI_API_KEY in .env

cd D:\DAMG7245_Big_Data_Systems\BigDataIA-SPring26-Team-4-case-study-5\cs5\src

uv run python -m exercises.agentic_due_diligence

# Expected output:
#   PE Org-AI-R: Agentic Due Diligence
#   Running full assessment for NVDA...
#   Company: NVDA
#   Org-AI-R Score: XX.X
#   HITL Required: True/False
#   ... agent messages ...


# ──────────────────────────────────────────────────────────────
# TROUBLESHOOTING
# ──────────────────────────────────────────────────────────────

# "uv not found"
#   → Install uv: powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
#   → Or: pip install uv

# "ModuleNotFoundError: No module named 'services'"
#   → Make sure you're running from cs5/src/ directory
#   → Or check sys.path includes cs5/src

# "Connection refused" on port 8000
#   → Docker isn't running. Do: docker compose -f docker/compose.yaml up -d

# "Failed to connect to CS1-CS4" in Streamlit
#   → Same as above — Docker needs to be running

# pytest errors about imports
#   → Make sure you ran: uv sync --all-extras
#   → Check that conftest.py adds src/ to path

# Claude Desktop doesn't show MCP server
#   → Check the config JSON is valid (no trailing commas)
#   → Restart Claude Desktop completely (not just close window)
#   → Check that the path in config matches your actual cs5 location
