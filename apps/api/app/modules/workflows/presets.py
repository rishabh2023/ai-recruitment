"""Predefined funnel blueprints (starter hiring workflows).

Code-defined, read-only presets shown on the Funnels page so a new org can start from a
sensible template instead of a blank funnel. Instantiating a preset just creates a normal
funnel (POST /funnels) from its stages — presets themselves are never stored or mutated.
Stage shape matches StageEditIn (name, purpose, execution_type, information_requirements,
requires_human_approval, criteria[{name, kind, weight}]).
"""

from __future__ import annotations

_SCREEN = {
    "name": "Initial screening",
    "purpose": "Confirm interest and basic hiring/logistical fit",
    "execution_type": "ai",
    "information_requirements": ["interest", "current_ctc", "expected_ctc", "notice_period", "location"],
    "requires_human_approval": False,
    "criteria": [{"name": "Basic eligibility", "kind": "rule", "weight": None}],
}
_HM_REVIEW = {
    "name": "Hiring manager review",
    "purpose": "Human review of evidence and decision",
    "execution_type": "human",
    "information_requirements": [],
    "requires_human_approval": True,
    "criteria": [],
}
_HR_OFFER = {
    "name": "HR & offer",
    "purpose": "Final HR check and offer rollout",
    "execution_type": "human",
    "information_requirements": [],
    "requires_human_approval": True,
    "criteria": [],
}


PRESETS: list[dict] = [
    {
        "key": "engineering",
        "name": "Engineering — screen → technical → HM review",
        "description": "AI screen, a weighted technical assessment, then a human hiring-manager decision.",
        "stages": [
            _SCREEN,
            {
                "name": "Technical assessment",
                "purpose": "Evaluate engineering competencies",
                "execution_type": "ai",
                "information_requirements": [],
                "requires_human_approval": False,
                "criteria": [
                    {"name": "Backend / API engineering", "kind": "numeric", "weight": 30.0},
                    {"name": "Problem solving", "kind": "numeric", "weight": 25.0},
                    {"name": "System design", "kind": "numeric", "weight": 20.0},
                    {"name": "Applied AI / LLM", "kind": "numeric", "weight": 15.0},
                    {"name": "Communication", "kind": "numeric", "weight": 10.0},
                ],
            },
            _HM_REVIEW,
            _HR_OFFER,
        ],
    },
    {
        "key": "sales",
        "name": "Sales — screen → assessment → HM review",
        "description": "AI screen, a sales-skills assessment, then a human hiring-manager decision.",
        "stages": [
            _SCREEN,
            {
                "name": "Sales assessment",
                "purpose": "Evaluate discovery, objection handling, communication",
                "execution_type": "ai",
                "information_requirements": [],
                "requires_human_approval": False,
                "criteria": [
                    {"name": "Discovery", "kind": "numeric", "weight": 30.0},
                    {"name": "Objection handling", "kind": "numeric", "weight": 30.0},
                    {"name": "Communication", "kind": "numeric", "weight": 40.0},
                ],
            },
            _HM_REVIEW,
            _HR_OFFER,
        ],
    },
    {
        "key": "general",
        "name": "General — screen → assessment → HM review",
        "description": "A role-agnostic three-step funnel: AI screen, role assessment, human decision.",
        "stages": [
            _SCREEN,
            {
                "name": "Role assessment",
                "purpose": "Evaluate configured role competencies",
                "execution_type": "ai",
                "information_requirements": [],
                "requires_human_approval": False,
                "criteria": [{"name": "Role fit", "kind": "numeric", "weight": 100.0}],
            },
            _HM_REVIEW,
        ],
    },
]
