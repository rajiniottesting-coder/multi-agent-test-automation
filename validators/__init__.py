"""Static checks run against LLM-generated code before it reaches a PR.

These are the reason generated tests are trustworthy: each one catches a
class of hallucination that would otherwise surface as a runtime failure
and look like a test bug.

    gherkin_analyzer               feature/step-def parsing and coverage
    import_validator               imports that do not resolve
    method_resolution_validator    page-object methods that do not exist
    orphan_cleanup                 dead code left by ai-update
"""
