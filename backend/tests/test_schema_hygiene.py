"""Everything in the output schema is sent to the model as instruction.

Pydantic will happily lift class docstrings into schema descriptions, which
quietly ships internal implementation rationale to the model as guidance.
These tests keep that from creeping back in.
"""

import json

from app.schemas import ANALYSIS_SCHEMA


def all_keys(node):
    if isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from all_keys(v)
    elif isinstance(node, list):
        for item in node:
            yield from all_keys(item)


def test_no_auto_generated_titles():
    """Pydantic emits titles like 'Overalltrustscore' — pure token noise.

    Checked as schema *keys*: the word "title" legitimately appears inside
    field descriptions, since the listing has a title.
    """
    assert "title" not in set(all_keys(ANALYSIS_SCHEMA))


def test_no_internal_rationale_leaks_to_the_model():
    rendered = json.dumps(ANALYSIS_SCHEMA).lower()
    for phrase in ("frontend", "original spec", "badge colour", "docstring", "popup"):
        assert phrase not in rendered, f"internal wording {phrase!r} leaked into schema"


def test_field_descriptions_survive():
    """Field-level descriptions are written for the model and must be kept."""
    props = ANALYSIS_SCHEMA["properties"]
    assert "holistic" in props["overallTrustScore"]["description"]
    assert props["findings"]["description"]
    assert props["specDiscrepancies"]["description"]

    sub = ANALYSIS_SCHEMA["properties"]["subScores"]["properties"]
    for name in ("visualIntegrity", "specConsistency", "priceSanity"):
        assert sub[name]["description"].startswith("0-100")


def test_object_nodes_carry_no_description():
    def objects(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                yield node
            for v in node.values():
                yield from objects(v)
        elif isinstance(node, list):
            for i in node:
                yield from objects(i)

    for obj in objects(ANALYSIS_SCHEMA):
        assert "description" not in obj
