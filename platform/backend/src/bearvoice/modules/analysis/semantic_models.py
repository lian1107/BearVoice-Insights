from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


SignalType = Literal[
    "defect",
    "cognition",
    "expectation",
    "consultation",
    "safety",
    "innovation",
    "service",
]
LifecycleStage = Literal[
    "pre_purchase",
    "onboarding",
    "use",
    "maintenance",
    "after_sales",
    "unknown",
]
RiskLevel = Literal["low", "medium", "high", "critical"]


class SemanticSignal(BaseModel):
    """A single evidence-backed signal. All keys are required in model output."""

    model_config = ConfigDict(extra="forbid", strict=True)

    signal_type: SignalType
    lifecycle_stage: LifecycleStage
    object_name: str | None
    issue: str = Field(min_length=1, max_length=500)
    latent_need: str | None
    scenario: str | None
    evidence_text: str = Field(min_length=1, max_length=2_000)
    confidence: float = Field(ge=0.0, le=1.0)
    uncalibrated: Literal[True]
    risk_level: RiskLevel
    root_cause_hypotheses: list[str] = Field(max_length=5)
    missing_information: list[str] = Field(max_length=10)
    improvement_directions: list[str] = Field(max_length=5)
    validation_suggestions: list[str] = Field(max_length=5)

    @model_validator(mode="after")
    def validate_lists(self) -> Self:
        for name, values in (
            ("root_cause_hypotheses", self.root_cause_hypotheses),
            ("missing_information", self.missing_information),
            ("improvement_directions", self.improvement_directions),
            ("validation_suggestions", self.validation_suggestions),
        ):
            if any(not value.strip() for value in values):
                raise ValueError(f"{name} cannot contain blank items")
        return self


class VoiceSemanticResult(BaseModel):
    """Strict JSON contract returned by a semantic extraction model."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["1.0"]
    voice_id: str = Field(min_length=1, max_length=200)
    signals: list[SemanticSignal] = Field(max_length=20)


class VoiceSemanticInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voice_id: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=20_000)
    product_name: str | None = Field(default=None, max_length=300)
