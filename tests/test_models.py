"""
Pydantic model validation tests for PE Org-AI-R Platform.

Tests all model validations, validators, and business logic.
"""

import pytest
from datetime import datetime
from uuid import uuid4, UUID
from pydantic import ValidationError

from app.models.company import (
    CompanyCreate,
    CompanyUpdate,
    CompanyResponse,
    IndustryCreate,
)
from app.models.assessment import (
    AssessmentCreate,
    AssessmentUpdate,
    AssessmentResponse,
    AssessmentType,
    AssessmentStatus,
    validate_status_transition,
    get_allowed_transitions,
)
from app.models.dimension import (
    DimensionScoreCreate,
    DimensionScoreUpdate,
    Dimension,
    DIMENSION_WEIGHTS,
    get_dimension_weight,
    validate_dimension_scores_complete,
    get_missing_dimensions,
)


# ===========================================================================
# Company Model Tests
# ===========================================================================

class TestCompanyModel:
    """Test Company model validation."""
    
    def test_company_create_valid(self):
        """Test creating valid company."""
        company = CompanyCreate(
            name="Test Corp",
            ticker="TEST",
            industry_id=uuid4(),
            position_factor=0.5
        )
        assert company.name == "Test Corp"
        assert company.ticker == "TEST"
        assert company.position_factor == 0.5
    
    def test_ticker_uppercase_conversion(self):
        """Test ticker is converted to uppercase."""
        company = CompanyCreate(
            name="Test",
            ticker="test",  # lowercase
            industry_id=uuid4(),
            position_factor=0.0
        )
        assert company.ticker == "TEST"  # Should be uppercase
    
    def test_ticker_optional(self):
        """Test ticker can be None."""
        company = CompanyCreate(
            name="Test",
            industry_id=uuid4(),
            position_factor=0.0
        )
        assert company.ticker is None
    
    def test_position_factor_range_validation(self):
        """Test position_factor must be between -1 and 1."""
        # Valid range
        company = CompanyCreate(
            name="Test",
            industry_id=uuid4(),
            position_factor=-1.0
        )
        assert company.position_factor == -1.0
        
        # Out of range should fail
        with pytest.raises(ValidationError):
            CompanyCreate(
                name="Test",
                industry_id=uuid4(),
                position_factor=2.0  # Too high
            )
    
    def test_name_length_validation(self):
        """Test name length constraints."""
        # Too short
        with pytest.raises(ValidationError):
            CompanyCreate(
                name="",
                industry_id=uuid4(),
                position_factor=0.0
            )
        
        # Too long
        with pytest.raises(ValidationError):
            CompanyCreate(
                name="A" * 256,  # Max 255
                industry_id=uuid4(),
                position_factor=0.0
            )


class TestIndustryModel:
    """Test Industry model validation."""
    
    def test_industry_create_valid(self):
        """Test creating valid industry."""
        industry = IndustryCreate(
            name="Technology",
            sector="IT Services",
            h_r_base=75.0
        )
        assert industry.name == "Technology"
        assert industry.h_r_base == 75.0
    
    def test_h_r_base_range(self):
        """Test h_r_base must be 0-100."""
        # Valid
        industry = IndustryCreate(
            name="Tech",
            sector="IT",
            h_r_base=100.0
        )
        assert industry.h_r_base == 100.0
        
        # Out of range
        with pytest.raises(ValidationError):
            IndustryCreate(
                name="Tech",
                sector="IT",
                h_r_base=150.0
            )


# ===========================================================================
# Assessment Model Tests
# ===========================================================================

class TestAssessmentModel:
    """Test Assessment model validation."""
    
    def test_assessment_create_valid(self):
        """Test creating valid assessment."""
        assessment = AssessmentCreate(
            company_id=uuid4(),
            assessment_type=AssessmentType.SCREENING,
            assessment_date=datetime.now(),
            primary_assessor="John Doe"
        )
        assert assessment.assessment_type == AssessmentType.SCREENING
        assert assessment.primary_assessor == "John Doe"
    
    def test_assessment_types_enum(self):
        """Test all assessment types from PDF."""
        types = [
            AssessmentType.SCREENING,
            AssessmentType.DUE_DILIGENCE,
            AssessmentType.QUARTERLY,
            AssessmentType.EXIT_PREP,
        ]
        assert len(types) == 4
        assert AssessmentType.SCREENING.value == "screening"
        assert AssessmentType.DUE_DILIGENCE.value == "due_diligence"
    
    def test_assessment_status_enum(self):
        """Test all assessment statuses from PDF."""
        statuses = [
            AssessmentStatus.DRAFT,
            AssessmentStatus.IN_PROGRESS,
            AssessmentStatus.SUBMITTED,
            AssessmentStatus.APPROVED,
            AssessmentStatus.SUPERSEDED,
        ]
        assert len(statuses) == 5
        assert AssessmentStatus.DRAFT.value == "draft"
    
    def test_confidence_interval_validation(self):
        """Test confidence interval validation."""
        # Valid interval
        assessment = AssessmentResponse(
            id=uuid4(),
            company_id=uuid4(),
            assessment_type=AssessmentType.SCREENING,
            assessment_date=datetime.now(),
            status=AssessmentStatus.DRAFT,
            confidence_lower=70.0,
            confidence_upper=90.0,
            created_at=datetime.now()
        )
        assert assessment.confidence_lower == 70.0
        assert assessment.confidence_upper == 90.0
        
        # Invalid interval (upper < lower)
        with pytest.raises(ValidationError):
            AssessmentResponse(
                id=uuid4(),
                company_id=uuid4(),
                assessment_type=AssessmentType.SCREENING,
                assessment_date=datetime.now(),
                status=AssessmentStatus.DRAFT,
                confidence_lower=90.0,
                confidence_upper=70.0,  # Lower than lower bound
                created_at=datetime.now()
            )


class TestAssessmentStateMachine:
    """Test assessment status state machine."""
    
    def test_valid_transitions(self):
        """Test all valid state transitions."""
        # DRAFT -> IN_PROGRESS
        assert validate_status_transition(
            AssessmentStatus.DRAFT,
            AssessmentStatus.IN_PROGRESS
        ) is True
        
        # IN_PROGRESS -> SUBMITTED
        assert validate_status_transition(
            AssessmentStatus.IN_PROGRESS,
            AssessmentStatus.SUBMITTED
        ) is True
        
        # SUBMITTED -> APPROVED
        assert validate_status_transition(
            AssessmentStatus.SUBMITTED,
            AssessmentStatus.APPROVED
        ) is True
    
    def test_invalid_transitions(self):
        """Test invalid state transitions are rejected."""
        # DRAFT -> APPROVED (skipping states)
        assert validate_status_transition(
            AssessmentStatus.DRAFT,
            AssessmentStatus.APPROVED
        ) is False
        
        # APPROVED -> DRAFT (backwards)
        assert validate_status_transition(
            AssessmentStatus.APPROVED,
            AssessmentStatus.DRAFT
        ) is False
        
        # SUPERSEDED -> anything (terminal state)
        assert validate_status_transition(
            AssessmentStatus.SUPERSEDED,
            AssessmentStatus.DRAFT
        ) is False
    
    def test_get_allowed_transitions(self):
        """Test getting allowed transitions for each status."""
        # DRAFT can go to IN_PROGRESS or SUPERSEDED
        allowed = get_allowed_transitions(AssessmentStatus.DRAFT)
        assert AssessmentStatus.IN_PROGRESS in allowed
        assert AssessmentStatus.SUPERSEDED in allowed
        
        # SUPERSEDED has no allowed transitions (terminal)
        allowed = get_allowed_transitions(AssessmentStatus.SUPERSEDED)
        assert len(allowed) == 0


# ===========================================================================
# Dimension Score Model Tests
# ===========================================================================

class TestDimensionScoreModel:
    """Test DimensionScore model validation."""
    
    def test_dimension_score_create_valid(self):
        """Test creating valid dimension score."""
        score = DimensionScoreCreate(
            assessment_id=uuid4(),
            dimension=Dimension.DATA_INFRASTRUCTURE,
            score=85.0,
            weight=0.25,
            confidence=0.9,
            evidence_count=10
        )
        assert score.score == 85.0
        assert score.dimension == Dimension.DATA_INFRASTRUCTURE
    
    def test_auto_weight_assignment(self):
        """Test automatic weight assignment per PDF Section 3.2.4."""
        score = DimensionScoreCreate(
            assessment_id=uuid4(),
            dimension=Dimension.DATA_INFRASTRUCTURE,
            score=80.0,
            confidence=0.8,
            evidence_count=5
            # weight not provided - should auto-assign
        )
        # Should get default weight for DATA_INFRASTRUCTURE
        assert score.weight == 0.25
    
    def test_dimension_weights_sum_to_one(self):
        """Test that all dimension weights sum to 1.0."""
        total = sum(DIMENSION_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001  # Allow floating point precision
    
    def test_all_seven_dimensions(self):
        """Test all 7 dimensions from PDF Table 1."""
        dimensions = [
            Dimension.DATA_INFRASTRUCTURE,
            Dimension.AI_GOVERNANCE,
            Dimension.TECHNOLOGY_STACK,
            Dimension.TALENT_SKILLS,
            Dimension.LEADERSHIP_VISION,
            Dimension.USE_CASE_PORTFOLIO,
            Dimension.CULTURE_CHANGE,
        ]
        assert len(dimensions) == 7
        
        # Verify weights per PDF Table 1
        assert get_dimension_weight(Dimension.DATA_INFRASTRUCTURE) == 0.25
        assert get_dimension_weight(Dimension.AI_GOVERNANCE) == 0.20
        assert get_dimension_weight(Dimension.TECHNOLOGY_STACK) == 0.15
        assert get_dimension_weight(Dimension.TALENT_SKILLS) == 0.15
        assert get_dimension_weight(Dimension.LEADERSHIP_VISION) == 0.10
        assert get_dimension_weight(Dimension.USE_CASE_PORTFOLIO) == 0.10
        assert get_dimension_weight(Dimension.CULTURE_CHANGE) == 0.05
    
    def test_score_range_validation(self):
        """Test score must be 0-100."""
        # Valid scores
        for score_value in [0.0, 50.0, 100.0]:
            score = DimensionScoreCreate(
                assessment_id=uuid4(),
                dimension=Dimension.DATA_INFRASTRUCTURE,
                score=score_value,
                weight=0.25,
                confidence=0.8,
                evidence_count=5
            )
            assert score.score == score_value
        
        # Out of range
        with pytest.raises(ValidationError):
            DimensionScoreCreate(
                assessment_id=uuid4(),
                dimension=Dimension.DATA_INFRASTRUCTURE,
                score=150.0,  # Too high
                weight=0.25,
                confidence=0.8,
                evidence_count=5
            )
    
    def test_validate_complete_scores(self):
        """Test validation of complete dimension score set."""
        # Create all 7 dimension scores
        all_scores = [
            DimensionScoreCreate(
                assessment_id=uuid4(),
                dimension=dim,
                score=80.0,
                confidence=0.8,
                evidence_count=5
            )
            for dim in Dimension
        ]
        
        assert validate_dimension_scores_complete(all_scores) is True
        
        # Missing one dimension
        incomplete_scores = all_scores[:-1]  # Remove last one
        assert validate_dimension_scores_complete(incomplete_scores) is False
    
    def test_get_missing_dimensions(self):
        """Test identifying missing dimensions."""
        # Only score 2 dimensions
        partial_scores = [
            DimensionScoreCreate(
                assessment_id=uuid4(),
                dimension=Dimension.DATA_INFRASTRUCTURE,
                score=80.0,
                confidence=0.8,
                evidence_count=5
            ),
            DimensionScoreCreate(
                assessment_id=uuid4(),
                dimension=Dimension.AI_GOVERNANCE,
                score=75.0,
                confidence=0.8,
                evidence_count=5
            )
        ]
        
        missing = get_missing_dimensions(partial_scores)
        assert len(missing) == 5  # 7 total - 2 scored = 5 missing
        assert Dimension.TECHNOLOGY_STACK in missing
        assert Dimension.TALENT_SKILLS in missing


# ===========================================================================
# Integration Tests
# ===========================================================================

class TestModelIntegration:
    """Test models work together correctly."""
    
    def test_complete_assessment_workflow(self):
        """Test creating complete assessment with scores."""
        company_id = uuid4()
        
        # Create assessment
        assessment = AssessmentCreate(
            company_id=company_id,
            assessment_type=AssessmentType.SCREENING,
            assessment_date=datetime.now(),
            primary_assessor="John Doe",
            secondary_assessor="Jane Smith"
        )
        
        # Simulate assessment response
        assessment_id = uuid4()
        
        # Create all 7 dimension scores
        scores = []
        for dimension in Dimension:
            score = DimensionScoreCreate(
                assessment_id=assessment_id,
                dimension=dimension,
                score=80.0,
                confidence=0.85,
                evidence_count=10
            )
            scores.append(score)
        
        # Verify all dimensions present
        assert validate_dimension_scores_complete(scores) is True
        
        # Verify weights sum to 1.0
        total_weight = sum(s.weight for s in scores)
        assert abs(total_weight - 1.0) < 0.001
