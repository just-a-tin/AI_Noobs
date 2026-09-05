"""The Bedrock json_schema must satisfy structured-output rules, or every
production call 400s while mock mode stays happily green."""

from app.schemas import ANALYSIS_SCHEMA, AnalysisCore


def walk_objects(node):
    if isinstance(node, dict):
        if node.get("type") == "object" and "properties" in node:
            yield node
        for v in node.values():
            yield from walk_objects(v)
    elif isinstance(node, list):
        for item in node:
            yield from walk_objects(item)


def test_every_object_is_strict():
    objects = list(walk_objects(ANALYSIS_SCHEMA))
    assert objects, "schema should contain object nodes"
    for obj in objects:
        assert obj["additionalProperties"] is False
        assert set(obj["required"]) == set(obj["properties"])


def test_no_dangling_refs():
    """$defs are inlined; a leftover $ref would fail at request time."""
    rendered = repr(ANALYSIS_SCHEMA)
    assert "$ref" not in rendered
    assert "$defs" not in rendered


def test_top_level_shape_matches_spec():
    props = ANALYSIS_SCHEMA["properties"]
    for expected in (
        "overallTrustScore",
        "subScores",
        "scaleAnalysis",
        "findings",
        "imageAnalysis",
        "specDiscrepancies",
    ):
        assert expected in props

    # riskLevel is derived by the backend, never asked of the model.
    assert "riskLevel" not in props

    # listedLongestCm is parsed from the specs, not asked of the model.
    assert "listedLongestCm" not in props


def test_subscores_present_for_ui_breakdown():
    sub = ANALYSIS_SCHEMA["properties"]["subScores"]["properties"]
    assert set(sub) == {
        "visualIntegrity",
        "specConsistency",
        "priceSanity",
        "scaleFidelity",
    }


def test_scale_estimates_are_nullable():
    """Absolute size is unrecoverable without a reference object, so the model
    must be able to answer 'unknown' rather than invent a number."""
    scale = ANALYSIS_SCHEMA["properties"]["scaleAnalysis"]["properties"]

    for nullable in ("scaleReference", "expectedLongestCm", "apparentLongestCm"):
        rendered = repr(scale[nullable])
        assert "null" in rendered, f"{nullable} must permit null"

    # The confidence enum must offer an explicit "cannot tell" value.
    assert "NONE" in repr(scale["scaleConfidence"])


def test_mock_verdicts_validate_against_model():
    from app.mocks import _PERSONAS

    for persona in _PERSONAS:
        AnalysisCore.model_validate(persona.model_dump())
