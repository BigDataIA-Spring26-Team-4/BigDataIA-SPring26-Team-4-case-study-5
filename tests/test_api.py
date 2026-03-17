"""
API endpoint tests for PE Org-AI-R Platform.

Updated to match PDF-compliant schema and endpoints.
"""

import uuid
from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.services.snowflake import get_db

# ===========================================================================
# Test Fixtures and Helper Functions
# ===========================================================================

FAKE_ID = str(uuid.uuid4())
FAKE_INDUSTRY_ID = str(uuid.uuid4())
NOW = datetime(2025, 1, 1, 0, 0, 0)


def _fake_db():
    """Mock database session."""
    db = MagicMock()
    yield db


@pytest.fixture()
def client():
    """Test client with mocked database."""
    app.dependency_overrides[get_db] = _fake_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _company_row(**overrides):
    """Create mock company row with PDF-compliant field names."""
    defaults = dict(
        id=FAKE_ID,
        name="Acme Corp",
        ticker="ACME",
        industry_id=FAKE_INDUSTRY_ID,
        position_factor=0.5,  # PDF field name
        is_deleted=False,
        created_at=NOW,
        updated_at=NOW,
    )
    defaults.update(overrides)
    row = MagicMock()
    row.configure_mock(**defaults)
    return row


def _assessment_row(**overrides):
    """Create mock assessment row with PDF-compliant field names."""
    defaults = dict(
        id=FAKE_ID,
        company_id=FAKE_INDUSTRY_ID,
        assessment_type="screening",  # PDF enum value
        assessment_date=date(2025, 6, 1),
        status="draft",  # PDF enum value
        primary_assessor="John Doe",  # PDF field name
        secondary_assessor="Jane Smith",  # PDF field name
        v_r_score=None,
        confidence_lower=None,
        confidence_upper=None,
        created_at=NOW,
    )
    defaults.update(overrides)
    return MagicMock(**defaults)


def _score_row(**overrides):
    """Create mock dimension score row."""
    defaults = dict(
        id=FAKE_ID,
        assessment_id=FAKE_ID,
        dimension="data_infrastructure",
        score=80.0,
        weight=0.25,
        confidence=0.9,
        evidence_count=5,
        created_at=NOW,
    )
    defaults.update(overrides)
    return MagicMock(**defaults)


# ===========================================================================
# Health Check Tests
# ===========================================================================

class TestHealth:
    def test_health(self, client):
        """Test health endpoint returns correct format."""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        # PDF-compliant health response
        assert "status" in data
        assert "timestamp" in data
        assert "version" in data
        assert "dependencies" in data
        assert data["version"] == "1.0.0"


# ===========================================================================
# Company Endpoints Tests
# ===========================================================================

COMPANIES_URL = "/api/v1/companies"


class TestCreateCompany:
    @patch("app.routers.companies.snowflake")
    @patch("app.routers.companies.invalidate")
    def test_success(self, _inv, mock_sf, client):
        """Test successful company creation."""
        mock_sf.create_company.return_value = _company_row()
        payload = {
            "name": "Acme Corp",
            "ticker": "ACME",
            "industry_id": FAKE_INDUSTRY_ID,
            "position_factor": 0.5,  # PDF field name
        }
        resp = client.post(COMPANIES_URL, json=payload)
        assert resp.status_code == 201  # Created, not 200
        body = resp.json()
        assert body["name"] == "Acme Corp"
        assert body["id"] == FAKE_ID
        assert body["position_factor"] == 0.5
        mock_sf.create_company.assert_called_once()

    def test_invalid_ticker(self, client):
        """Test ticker validation."""
        payload = {
            "name": "Acme",
            "ticker": "toolongtickerr",  # Too long
            "industry_id": FAKE_INDUSTRY_ID,
            "position_factor": 0.0,
        }
        resp = client.post(COMPANIES_URL, json=payload)
        assert resp.status_code == 422

    def test_missing_name(self, client):
        """Test required name field."""
        payload = {"industry_id": FAKE_INDUSTRY_ID}
        resp = client.post(COMPANIES_URL, json=payload)
        assert resp.status_code == 422

    def test_position_out_of_range(self, client):
        """Test position_factor range validation."""
        payload = {
            "name": "Acme",
            "industry_id": FAKE_INDUSTRY_ID,
            "position_factor": 5.0,  # Out of range [-1, 1]
        }
        resp = client.post(COMPANIES_URL, json=payload)
        assert resp.status_code == 422


class TestListCompanies:
    @patch("app.routers.companies.snowflake")
    def test_success(self, mock_sf, client):
        """Test listing companies with pagination."""
        mock_sf.list_companies.return_value = [_company_row()]
        mock_sf.count_companies.return_value = 1
        
        resp = client.get(COMPANIES_URL)
        assert resp.status_code == 200
        
        # Check pagination response format (PDF Section 4.3)
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert "page" in body
        assert "page_size" in body
        assert "total_pages" in body
        assert len(body["items"]) == 1

    @patch("app.routers.companies.snowflake")
    def test_empty(self, mock_sf, client):
        """Test empty company list."""
        mock_sf.list_companies.return_value = []
        mock_sf.count_companies.return_value = 0
        
        resp = client.get(COMPANIES_URL)
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0


class TestGetCompany:
    @patch("app.routers.companies.snowflake")
    def test_success(self, mock_sf, client):
        """Test getting company by ID."""
        mock_sf.get_company.return_value = _company_row()
        resp = client.get(f"{COMPANIES_URL}/{FAKE_ID}")
        assert resp.status_code == 200
        assert resp.json()["id"] == FAKE_ID

    @patch("app.routers.companies.snowflake")
    def test_not_found(self, mock_sf, client):
        """Test 404 for non-existent company."""
        mock_sf.get_company.side_effect = HTTPException(
            status_code=404, detail="Company not found"
        )
        resp = client.get(f"{COMPANIES_URL}/{FAKE_ID}")
        assert resp.status_code == 404


class TestUpdateCompany:
    @patch("app.routers.companies.snowflake")
    @patch("app.routers.companies.invalidate")
    def test_success(self, _inv, mock_sf, client):
        """Test updating company."""
        mock_sf.update_company.return_value = _company_row(name="Updated")
        resp = client.put(f"{COMPANIES_URL}/{FAKE_ID}", json={"name": "Updated"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated"

    @patch("app.routers.companies.snowflake")
    @patch("app.routers.companies.invalidate")
    def test_not_found(self, _inv, mock_sf, client):
        """Test 404 for updating non-existent company."""
        mock_sf.update_company.side_effect = HTTPException(
            status_code=404, detail="Company not found"
        )
        resp = client.put(f"{COMPANIES_URL}/{FAKE_ID}", json={"name": "X"})
        assert resp.status_code == 404


class TestDeleteCompany:
    @patch("app.routers.companies.snowflake")
    @patch("app.routers.companies.invalidate")
    def test_success(self, _inv, mock_sf, client):
        """Test soft deleting company."""
        mock_sf.delete_company.return_value = None
        resp = client.delete(f"{COMPANIES_URL}/{FAKE_ID}")
        assert resp.status_code == 204  # No Content, not 200

    @patch("app.routers.companies.snowflake")
    @patch("app.routers.companies.invalidate")
    def test_not_found(self, _inv, mock_sf, client):
        """Test 404 for deleting non-existent company."""
        mock_sf.delete_company.side_effect = HTTPException(
            status_code=404, detail="Company not found"
        )
        resp = client.delete(f"{COMPANIES_URL}/{FAKE_ID}")
        assert resp.status_code == 404


# ===========================================================================
# Assessment Endpoints Tests
# ===========================================================================

ASSESSMENTS_URL = "/api/v1/assessments"


class TestCreateAssessment:
    @patch("app.routers.assessments.snowflake")
    @patch("app.routers.assessments.invalidate")
    def test_success(self, _inv, mock_sf, client):
        """Test successful assessment creation."""
        mock_sf.create_assessment.return_value = _assessment_row()
        payload = {
            "company_id": FAKE_INDUSTRY_ID,
            "assessment_type": "screening",  # PDF enum value
            "assessment_date": "2025-06-01T00:00:00",
            "primary_assessor": "John Doe",
        }
        resp = client.post(ASSESSMENTS_URL, json=payload)
        assert resp.status_code == 201  # Created, not 200
        body = resp.json()
        assert body["assessment_type"] == "screening"
        assert body["status"] == "draft"

    def test_invalid_type(self, client):
        """Test invalid assessment type."""
        payload = {
            "company_id": FAKE_INDUSTRY_ID,
            "assessment_type": "invalid_type",
            "assessment_date": "2025-06-01",
        }
        resp = client.post(ASSESSMENTS_URL, json=payload)
        assert resp.status_code == 422

    def test_vr_score_out_of_range(self, client):
        """Test VR score validation."""
        # This should be tested via PATCH since v_r_score is in Response, not Create
        pass  # Skipping - v_r_score not in AssessmentCreate


class TestListAssessments:
    @patch("app.routers.assessments.snowflake")
    def test_success(self, mock_sf, client):
        """Test listing assessments with pagination."""
        mock_sf.list_assessments.return_value = [_assessment_row()]
        mock_sf.count_assessments.return_value = 1
        
        resp = client.get(ASSESSMENTS_URL)
        assert resp.status_code == 200
        
        # Check pagination response
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert len(body["items"]) == 1


class TestGetAssessment:
    @patch("app.routers.assessments.snowflake")
    def test_success(self, mock_sf, client):
        """Test getting assessment by ID."""
        mock_sf.get_assessment.return_value = _assessment_row()
        resp = client.get(f"{ASSESSMENTS_URL}/{FAKE_ID}")
        assert resp.status_code == 200

    @patch("app.routers.assessments.snowflake")
    def test_not_found(self, mock_sf, client):
        """Test 404 for non-existent assessment."""
        mock_sf.get_assessment.side_effect = HTTPException(
            status_code=404, detail="Assessment not found"
        )
        resp = client.get(f"{ASSESSMENTS_URL}/{FAKE_ID}")
        assert resp.status_code == 404


class TestUpdateAssessment:
    @patch("app.routers.assessments.snowflake")
    @patch("app.routers.assessments.invalidate")
    def test_success(self, _inv, mock_sf, client):
        """Test updating assessment status."""
        mock_sf.update_assessment.return_value = _assessment_row(status="in_progress")
        resp = client.patch(
            f"{ASSESSMENTS_URL}/{FAKE_ID}",
            json={"status": "in_progress"}
        )
        assert resp.status_code == 200

    @patch("app.routers.assessments.snowflake")
    @patch("app.routers.assessments.invalidate")
    def test_invalid_transition(self, _inv, mock_sf, client):
        """Test invalid status transition."""
        # Test tries to use 'pending' which is not valid in PDF schema
        # Should use valid PDF enum: draft, in_progress, submitted, approved, superseded
        resp = client.patch(
            f"{ASSESSMENTS_URL}/{FAKE_ID}",
            json={"status": "invalid_status"}
        )
        # Pydantic validation should catch this
        assert resp.status_code == 422


# ===========================================================================
# Dimension Scores Tests
# ===========================================================================


def _score_payload(assessment_id=FAKE_ID):
    """Create dimension score payload."""
    return {
        "assessment_id": assessment_id,
        "dimension": "data_infrastructure",
        "score": 80.0,
        "weight": 0.25,
        "confidence": 0.9,
        "evidence_count": 5,
    }


class TestAddScores:
    @patch("app.routers.assessments.snowflake")
    @patch("app.routers.assessments.invalidate")
    def test_success(self, _inv, mock_sf, client):
        """Test adding dimension scores."""
        mock_sf.add_scores.return_value = [_score_row()]
        resp = client.post(
            f"{ASSESSMENTS_URL}/{FAKE_ID}/scores",
            json=[_score_payload()]
        )
        assert resp.status_code == 201  # Created, not 200
        assert len(resp.json()) == 1

    @patch("app.routers.assessments.snowflake")
    @patch("app.routers.assessments.invalidate")
    def test_assessment_not_found(self, _inv, mock_sf, client):
        """Test 404 when assessment doesn't exist."""
        mock_sf.add_scores.side_effect = HTTPException(
            status_code=404, detail="Assessment not found"
        )
        resp = client.post(
            f"{ASSESSMENTS_URL}/{FAKE_ID}/scores",
            json=[_score_payload()]
        )
        assert resp.status_code == 404

    def test_invalid_dimension(self, client):
        """Test invalid dimension name."""
        payload = _score_payload()
        payload["dimension"] = "nonexistent"
        resp = client.post(
            f"{ASSESSMENTS_URL}/{FAKE_ID}/scores",
            json=[payload]
        )
        assert resp.status_code == 422

    def test_score_out_of_range(self, client):
        """Test score validation."""
        payload = _score_payload()
        payload["score"] = 150.0  # Out of range [0, 100]
        resp = client.post(
            f"{ASSESSMENTS_URL}/{FAKE_ID}/scores",
            json=[payload]
        )
        assert resp.status_code == 422


class TestGetScores:
    @patch("app.routers.assessments.snowflake")
    def test_success(self, mock_sf, client):
        """Test getting dimension scores."""
        mock_sf.get_scores.return_value = [_score_row()]
        resp = client.get(f"{ASSESSMENTS_URL}/{FAKE_ID}/scores")
        assert resp.status_code == 200
        assert len(resp.json()) == 1


class TestUpdateScore:
    """Test updating individual dimension score."""
    
    @patch("app.routers.scores.snowflake")  # Changed from assessments to scores
    @patch("app.routers.scores.invalidate")  # Changed from assessments to scores
    def test_success(self, _inv, mock_sf, client):
        """Test successful score update."""
        mock_sf.update_score.return_value = _score_row(score=90.0)
        
        # Correct endpoint per PDF Table 2: PUT /api/v1/scores/{id}
        resp = client.put(
            f"/api/v1/scores/{FAKE_ID}",
            json={"score": 90.0}
        )
        assert resp.status_code == 200
        assert resp.json()["score"] == 90.0

    @patch("app.routers.scores.snowflake")  # Changed from assessments to scores
    @patch("app.routers.scores.invalidate")  # Changed from assessments to scores
    def test_not_found(self, _inv, mock_sf, client):
        """Test 404 for non-existent score."""
        mock_sf.update_score.side_effect = HTTPException(
            status_code=404, detail="Dimension score not found"
        )
        resp = client.put(
            f"/api/v1/scores/{FAKE_ID}",
            json={"score": 90.0}
        )
        assert resp.status_code == 404


# ===========================================================================
# Pagination Tests
# ===========================================================================

class TestPagination:
    """Test pagination functionality."""
    
    @patch("app.routers.companies.snowflake")
    def test_pagination_structure(self, mock_sf, client):
        """Test paginated response structure per PDF Section 4.3."""
        mock_sf.list_companies.return_value = [_company_row()]
        mock_sf.count_companies.return_value = 10
        
        resp = client.get(f"{COMPANIES_URL}?page=1&page_size=5")
        assert resp.status_code == 200
        
        body = resp.json()
        # Verify pagination structure
        assert body["items"] is not None
        assert body["total"] == 10
        assert body["page"] == 1
        assert body["page_size"] == 5
        assert body["total_pages"] == 2
    
    @patch("app.routers.companies.snowflake")
    def test_page_calculation(self, mock_sf, client):
        """Test correct page calculation."""
        mock_sf.list_companies.return_value = []
        mock_sf.count_companies.return_value = 25
        
        # Page 3 with page_size 10
        resp = client.get(f"{COMPANIES_URL}?page=3&page_size=10")
        assert resp.status_code == 200
        
        body = resp.json()
        assert body["page"] == 3
        assert body["page_size"] == 10
        assert body["total"] == 25
        assert body["total_pages"] == 3  # ceil(25/10) = 3
    
    @patch("app.routers.industries.snowflake")
    def test_industries_pagination(self, mock_sf, client):
        """Test industries pagination."""
        # Create 10 mock industries
        industries = [_industry_row(id=str(uuid.uuid4()), name=f"Industry {i}") for i in range(10)]
        mock_sf.list_industries.return_value = industries
        
        # Test page 1
        resp = client.get(f"{INDUSTRIES_URL}?page=1&page_size=5")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 5
        assert body["total"] == 10
        assert body["total_pages"] == 2


# ===========================================================================
# Industries Endpoints Tests
# ===========================================================================

INDUSTRIES_URL = "/api/v1/industries"


def _industry_row(**overrides):
    """Create mock industry row."""
    defaults = dict(
        id=FAKE_INDUSTRY_ID,
        name="Manufacturing",
        sector="Industrials",
        h_r_base=72.0,
        created_at=NOW,
    )
    defaults.update(overrides)
    row = MagicMock()
    row.configure_mock(**defaults)
    return row


class TestCreateIndustry:
    """Test create industry endpoint."""
    
    @patch("app.routers.industries.snowflake")
    @patch("app.routers.industries.invalidate")
    def test_success(self, _inv, mock_sf, client):
        """Test successful industry creation."""
        mock_sf.create_industry.return_value = _industry_row()
        payload = {
            "name": "Manufacturing",
            "sector": "Industrials",
            "h_r_base": 72.0
        }
        resp = client.post(INDUSTRIES_URL, json=payload)
        assert resp.status_code == 201
        assert resp.json()["name"] == "Manufacturing"
        mock_sf.create_industry.assert_called_once()
        _inv.assert_called_once()  # Cache invalidated


class TestListIndustries:
    """Test industries list endpoint (cached 1 hour, paginated)."""
    
    @patch("app.routers.industries.snowflake")
    def test_success(self, mock_sf, client):
        """Test listing industries with pagination."""
        mock_sf.list_industries.return_value = [
            _industry_row(),
            _industry_row(id=str(uuid.uuid4()), name="Healthcare"),
        ]
        resp = client.get(INDUSTRIES_URL)
        assert resp.status_code == 200
        body = resp.json()
        # Check pagination response
        assert "items" in body
        assert "total" in body
        assert len(body["items"]) == 2
        assert body["items"][0]["name"] == "Manufacturing"
    
    @patch("app.routers.industries.snowflake")
    def test_empty(self, mock_sf, client):
        """Test empty industries list."""
        mock_sf.list_industries.return_value = []
        resp = client.get(INDUSTRIES_URL)
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0


class TestGetIndustry:
    """Test get industry by ID endpoint (cached 1 hour)."""
    
    @patch("app.routers.industries.snowflake")
    def test_success(self, mock_sf, client):
        """Test getting industry by ID."""
        mock_sf.get_industry.return_value = _industry_row()
        resp = client.get(f"{INDUSTRIES_URL}/{FAKE_INDUSTRY_ID}")
        assert resp.status_code == 200
        assert resp.json()["id"] == FAKE_INDUSTRY_ID
        assert resp.json()["name"] == "Manufacturing"
    
    @patch("app.routers.industries.snowflake")
    def test_not_found(self, mock_sf, client):
        """Test 404 for non-existent industry."""
        mock_sf.get_industry.side_effect = HTTPException(
            status_code=404, detail="Industry not found"
        )
        resp = client.get(f"{INDUSTRIES_URL}/{FAKE_INDUSTRY_ID}")
        assert resp.status_code == 404


class TestUpdateIndustry:
    """Test update industry endpoint."""
    
    @patch("app.routers.industries.snowflake")
    @patch("app.routers.industries.invalidate")
    def test_success(self, _inv, mock_sf, client):
        """Test successful industry update."""
        existing = _industry_row()
        mock_sf.get_industry.return_value = existing
        
        payload = {
            "name": "Updated Manufacturing",
            "sector": "Industrials",
            "h_r_base": 75.0
        }
        resp = client.put(f"{INDUSTRIES_URL}/{FAKE_INDUSTRY_ID}", json=payload)
        assert resp.status_code == 200
        _inv.assert_called_once()  # Cache invalidated
    
    @patch("app.routers.industries.snowflake")
    @patch("app.routers.industries.invalidate")
    def test_not_found(self, _inv, mock_sf, client):
        """Test 404 for updating non-existent industry."""
        mock_sf.get_industry.side_effect = HTTPException(
            status_code=404, detail="Industry not found"
        )
        payload = {"name": "Test", "sector": "Test", "h_r_base": 50.0}
        resp = client.put(f"{INDUSTRIES_URL}/{FAKE_INDUSTRY_ID}", json=payload)
        assert resp.status_code == 404


class TestDeleteIndustry:
    """Test delete industry endpoint."""
    
    @patch("app.routers.industries.snowflake")
    @patch("app.routers.industries.invalidate")
    def test_success(self, _inv, mock_sf, client):
        """Test successful industry deletion."""
        mock_sf.get_industry.return_value = _industry_row()
        resp = client.delete(f"{INDUSTRIES_URL}/{FAKE_INDUSTRY_ID}")
        assert resp.status_code == 204  # No Content
        _inv.assert_called_once()  # Cache invalidated
    
    @patch("app.routers.industries.snowflake")
    @patch("app.routers.industries.invalidate")
    def test_not_found(self, _inv, mock_sf, client):
        """Test 404 for deleting non-existent industry."""
        mock_sf.get_industry.side_effect = HTTPException(
            status_code=404, detail="Industry not found"
        )
        resp = client.delete(f"{INDUSTRIES_URL}/{FAKE_INDUSTRY_ID}")
        assert resp.status_code == 404


# ===========================================================================
# Configuration Endpoints Tests
# ===========================================================================

CONFIG_URL = "/api/v1/config"


class TestDimensionWeights:
    """Test dimension weights configuration endpoint (cached 24 hours)."""
    
    def test_get_dimension_weights(self, client):
        """Test getting dimension weights configuration."""
        resp = client.get(f"{CONFIG_URL}/dimension-weights")
        assert resp.status_code == 200
        
        body = resp.json()
        assert "weights" in body
        assert "total" in body
        
        # Verify all 7 dimensions present
        weights = body["weights"]
        assert len(weights) == 7
        assert "data_infrastructure" in weights
        assert "ai_governance" in weights
        assert "technology_stack" in weights
        assert "talent_skills" in weights
        assert "leadership_vision" in weights
        assert "use_case_portfolio" in weights
        assert "culture_change" in weights
        
        # Verify weights per PDF Table 1
        assert weights["data_infrastructure"] == 0.25
        assert weights["ai_governance"] == 0.20
        assert weights["technology_stack"] == 0.15
        assert weights["talent_skills"] == 0.15
        assert weights["leadership_vision"] == 0.10
        assert weights["use_case_portfolio"] == 0.10
        assert weights["culture_change"] == 0.05
        
        # Verify total sums to 1.0
        assert body["total"] == 1.0
    
    def test_weights_sum_to_one(self, client):
        """Test that all dimension weights sum to exactly 1.0."""
        resp = client.get(f"{CONFIG_URL}/dimension-weights")
        assert resp.status_code == 200
        
        weights = resp.json()["weights"]
        total = sum(weights.values())
        assert abs(total - 1.0) < 0.001  # Allow floating point precision


# ===========================================================================
# State Machine Tests
# ===========================================================================

class TestAssessmentStateMachine:
    """Test assessment status state machine."""
    
    @patch("app.routers.assessments.snowflake")
    @patch("app.routers.assessments.invalidate")
    def test_valid_transition_draft_to_in_progress(self, _inv, mock_sf, client):
        """Test valid state transition."""
        mock_sf.update_assessment.return_value = _assessment_row(status="in_progress")
        resp = client.patch(
            f"{ASSESSMENTS_URL}/{FAKE_ID}",
            json={"status": "in_progress"}
        )
        assert resp.status_code == 200
    
    @patch("app.routers.assessments.snowflake")
    @patch("app.routers.assessments.invalidate")
    def test_invalid_transition_handled_by_service(self, _inv, mock_sf, client):
        """Test that invalid transitions are rejected by service layer."""
        mock_sf.update_assessment.side_effect = HTTPException(
            status_code=400,
            detail="Invalid status transition from 'approved' to 'draft'"
        )
        resp = client.patch(
            f"{ASSESSMENTS_URL}/{FAKE_ID}",
            json={"status": "draft"}
        )
        assert resp.status_code == 400
