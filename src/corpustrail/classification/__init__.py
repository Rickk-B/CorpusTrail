"""Optional, non-authoritative broad-corpus assessment infrastructure."""

from .contracts import (
    Assessment, AssessmentFailure, AssessmentPlan, AuditProtocol, Budgets,
    CalibrationBinding, EngineDescription, EngineRequest, ExecutionUnit,
    ClassifierPolicy, Score, ValidationProtocol,
)
from .registry import EngineRegistry
from .service import ClassificationService

__all__ = [
    'Assessment', 'AssessmentFailure', 'AssessmentPlan', 'AuditProtocol', 'Budgets',
    'CalibrationBinding', 'EngineDescription', 'EngineRequest', 'ExecutionUnit',
    'ClassifierPolicy', 'Score', 'ValidationProtocol', 'EngineRegistry', 'ClassificationService',
]
