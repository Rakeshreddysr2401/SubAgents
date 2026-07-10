"""AGENT_SPECS is the single source of truth for the swarm's shape —
constants, descriptions and specs must never drift apart."""

from src.commons.constants import AGENT_DESCRIPTIONS, AGENTS, CONVERSATION
from src.graph.registry import AGENT_SPECS


def test_specs_cover_exactly_the_agent_constants():
    assert set(AGENT_SPECS) == AGENTS
    assert set(AGENT_DESCRIPTIONS) == AGENTS


def test_spec_names_match_their_keys():
    for name, spec in AGENT_SPECS.items():
        assert spec.name == name


def test_default_agent_is_registered():
    assert CONVERSATION in AGENT_SPECS


def test_exactly_one_vision_and_one_deep_agent():
    assert sum(1 for s in AGENT_SPECS.values() if s.vision) == 1
    assert sum(1 for s in AGENT_SPECS.values() if s.deep) == 1


def test_no_handoff_exclusions_reference_real_agents():
    for spec in AGENT_SPECS.values():
        for peer in spec.no_handoff_to:
            assert peer in AGENT_SPECS
            assert peer != spec.name


def test_mcp_agents_carry_unavailable_notes():
    for spec in AGENT_SPECS.values():
        if spec.mcp_provider:
            note = getattr(spec.prompt_module, "UNAVAILABLE_NOTE", "")
            assert "unavailable" in note.lower(), spec.name


def test_prompt_modules_build():
    for spec in AGENT_SPECS.values():
        prompt = spec.prompt_module.build_prompt()
        assert isinstance(prompt, str) and len(prompt) > 50
