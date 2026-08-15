from enum import StrEnum


class OpportunityStatus(StrEnum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    VALIDATING = "validating"
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ARCHIVED = "archived"

    def can_transition_to(self, target: "OpportunityStatus") -> bool:
        transitions = {
            self.DRAFT: {self.PENDING_REVIEW},
            self.PENDING_REVIEW: {
                self.DRAFT,
                self.ACCEPTED,
                self.REJECTED,
            },
            self.ACCEPTED: {
                self.VALIDATING,
                self.PLANNED,
                self.ARCHIVED,
            },
            self.REJECTED: {self.DRAFT, self.ARCHIVED},
            self.VALIDATING: {
                self.PLANNED,
                self.REJECTED,
                self.ARCHIVED,
            },
            self.PLANNED: {self.IN_PROGRESS, self.ARCHIVED},
            self.IN_PROGRESS: {self.COMPLETED, self.ARCHIVED},
            self.COMPLETED: {self.ARCHIVED},
            self.ARCHIVED: set(),
        }
        return target in transitions[self]


class ActionItemStatus(StrEnum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

    def can_transition_to(self, target: "ActionItemStatus") -> bool:
        transitions = {
            self.PLANNED: {self.IN_PROGRESS, self.COMPLETED, self.CANCELLED},
            self.IN_PROGRESS: {self.BLOCKED, self.COMPLETED, self.CANCELLED},
            self.BLOCKED: {self.IN_PROGRESS, self.CANCELLED},
            self.COMPLETED: set(),
            self.CANCELLED: set(),
        }
        return target in transitions[self]


class ReviewDecisionType(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_CHANGES = "request_changes"


class Permission(StrEnum):
    READ_VOICE = "read_voice"
    READ_ALL_PRODUCT_LINES = "read_all_product_lines"
    MANAGE_SOURCES = "manage_sources"
    RUN_ANALYSIS = "run_analysis"
    REVIEW_TAXONOMY = "review_taxonomy"
    REVIEW_OPPORTUNITY = "review_opportunity"
    MANAGE_EVALUATION = "manage_evaluation"
    ADMIN = "admin"
