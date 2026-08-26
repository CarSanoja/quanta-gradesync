from autocurricula.core.fleet.declarations import AgentDeclaration
from autocurricula.schemas.fleet import AgentLifecycle, Capability

STAGE_GRADE = "grade"
STAGE_AUDIT = "audit"
STAGE_RISK = "risk"
STAGE_VERIFY = "verify"
STAGE_OPTIMIZE = "optimize"

PRO = "gemini_pro_model"
FLASH = "gemini_flash_model"

GRADING_AGENT_ID = "grading-agent"
CURRICULUM_AUDITOR_ID = "curriculum-auditor"
RISK_DETECTOR_ID = "risk-detector"
ARMOR_SCREENER_ID = "armor-screener"
SECOND_OPINION_ID = "second-opinion-evaluator"
FALLBACK_EVALUATOR_ID = "fallback-evaluator"
SCHEMA_REPAIR_ID = "schema-repair-agent"
PROMPT_PROPOSER_ID = "prompt-proposer"
CALIBRATION_EVALUATOR_ID = "calibration-evaluator"
META_OPTIMIZER_GRADING_ID = "meta-optimizer-grading"
META_OPTIMIZER_AUDIT_ID = "meta-optimizer-audit"
EVIDENCE_TRANSCRIBER_ID = "evidence-transcriber"

AGENT_DECLARATIONS: tuple[AgentDeclaration, ...] = (
    AgentDeclaration(
        agent_id=GRADING_AGENT_ID,
        fleet_index=1,
        display_name="Grading agent",
        role=(
            "Multimodal rubric grading of handwritten pages, parallel fan-out per "
            "exam, evidence spans cited verbatim"
        ),
        stages=(STAGE_GRADE,),
        capabilities=(Capability.LLM_INVOKE,),
        model_setting=PRO,
        container_attr="grading_evaluator",
        prompt_variant_id="grading-v1",
    ),
    AgentDeclaration(
        agent_id=CURRICULUM_AUDITOR_ID,
        fleet_index=2,
        display_name="Curriculum auditor",
        role="Cross-references every grade against the ministry standard",
        stages=(STAGE_AUDIT,),
        capabilities=(Capability.LLM_INVOKE, Capability.FIRESTORE_READ),
        model_setting=FLASH,
        container_attr="auditor",
        prompt_variant_id="auditor-v1",
    ),
    AgentDeclaration(
        agent_id=RISK_DETECTOR_ID,
        fleet_index=3,
        display_name="Risk detector",
        role=(
            "Dropout early warning from z-scores and longitudinal slopes over L3 "
            "history; deterministic, no model call"
        ),
        stages=(STAGE_RISK,),
        capabilities=(Capability.FIRESTORE_READ,),
        container_attr="risk_detector",
    ),
    AgentDeclaration(
        agent_id=ARMOR_SCREENER_ID,
        fleet_index=4,
        display_name="Armor screener",
        role=(
            "Model Armor: detects handwritten prompt injection on the scanned page "
            "and forces quarantine"
        ),
        stages=(STAGE_GRADE,),
        capabilities=(Capability.LLM_INVOKE,),
        model_setting=FLASH,
    ),
    AgentDeclaration(
        agent_id=SECOND_OPINION_ID,
        fleet_index=5,
        display_name="Second-opinion evaluator",
        role=(
            "Bounded rework loop over quarantined exams; human-in-the-loop keeps the "
            "final decision"
        ),
        stages=(STAGE_VERIFY,),
        capabilities=(Capability.LLM_INVOKE,),
        model_setting=FLASH,
        container_attr="rework_evaluator",
        prompt_variant_id="grading-v1",
    ),
    AgentDeclaration(
        agent_id=FALLBACK_EVALUATOR_ID,
        fleet_index=6,
        display_name="Fallback evaluator",
        role="Model failover on timeout or resource exhaustion, confidence discounted",
        stages=(STAGE_GRADE,),
        capabilities=(Capability.LLM_INVOKE,),
        model_setting=FLASH,
        container_attr="fallback_evaluator",
        prompt_variant_id="grading-v1",
    ),
    AgentDeclaration(
        agent_id=SCHEMA_REPAIR_ID,
        fleet_index=7,
        display_name="Schema repair agent",
        role=(
            "Bounded self-repair of malformed structured outputs before "
            "dead-lettering; deterministic retry loop that re-invokes the caller's "
            "own model rather than holding one of its own"
        ),
        stages=(STAGE_GRADE,),
        capabilities=(),
    ),
    AgentDeclaration(
        agent_id=PROMPT_PROPOSER_ID,
        fleet_index=8,
        display_name="Prompt proposer",
        role="Mutates grading and audit prompts for the tournament",
        stages=(STAGE_OPTIMIZE,),
        capabilities=(Capability.LLM_INVOKE,),
        model_setting=FLASH,
        prompt_variant_id="optimizer-v1",
    ),
    AgentDeclaration(
        agent_id=CALIBRATION_EVALUATOR_ID,
        fleet_index=9,
        display_name="Calibration evaluator",
        role="Re-grades human-scored samples to score each candidate prompt",
        stages=(STAGE_OPTIMIZE,),
        capabilities=(Capability.LLM_INVOKE,),
        model_setting=PRO,
    ),
    AgentDeclaration(
        agent_id=META_OPTIMIZER_GRADING_ID,
        fleet_index=10,
        display_name="Meta-optimizer (grading)",
        role=(
            "Tournament selection with adversarial anti-gaming validation and the "
            "composite objective gate over the grading prompt"
        ),
        stages=(STAGE_OPTIMIZE,),
        capabilities=(Capability.FIRESTORE_READ, Capability.FIRESTORE_WRITE),
        prompt_variant_id="grading-v1",
    ),
    AgentDeclaration(
        agent_id=META_OPTIMIZER_AUDIT_ID,
        fleet_index=11,
        display_name="Meta-optimizer (audit)",
        role=(
            "Tournament selection with anti-gaming validation and a scope-adjusted "
            "objective gate over the curriculum-audit prompt"
        ),
        stages=(STAGE_OPTIMIZE,),
        capabilities=(Capability.FIRESTORE_READ, Capability.FIRESTORE_WRITE),
        prompt_variant_id="auditor-v1",
    ),
    AgentDeclaration(
        agent_id=EVIDENCE_TRANSCRIBER_ID,
        fleet_index=12,
        display_name="Evidence transcriber",
        role=(
            "Second independent model reading of every scanned page, so the "
            "evidence the grader cites is verified against what the student "
            "actually wrote instead of going unchecked in production"
        ),
        stages=(STAGE_GRADE,),
        capabilities=(Capability.LLM_INVOKE,),
        model_setting=FLASH,
    ),
)

AGENTS_BY_ID: dict[str, AgentDeclaration] = {
    declaration.agent_id: declaration for declaration in AGENT_DECLARATIONS
}

OPTIMIZER_AGENTS: dict[str, str] = {
    META_OPTIMIZER_GRADING_ID: "grading-v1",
    META_OPTIMIZER_AUDIT_ID: "auditor-v1",
}

LIFECYCLE_DEFAULT = AgentLifecycle.ACTIVE
