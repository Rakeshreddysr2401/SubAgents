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


def test_mcp_agents_carry_reason_aware_unavailable_notes():
    for spec in AGENT_SPECS.values():
        if spec.mcp_provider:
            fn = getattr(spec.prompt_module, "unavailable_note", None)
            assert callable(fn), spec.name
            not_connected = fn("not_connected")
            expired = fn("expired")
            # Never-connected points at setup; expired points at re-auth. Both
            # explicitly forbid the misleading "try again later".
            assert "not connected yet" in not_connected.lower(), spec.name
            assert "settings" in not_connected.lower(), spec.name
            assert 'not say "try again later"' in not_connected.lower(), spec.name
            assert "expired" in expired.lower(), spec.name


def test_prompt_modules_build():
    for spec in AGENT_SPECS.values():
        prompt = spec.prompt_module.build_prompt()
        assert isinstance(prompt, str) and len(prompt) > 50
