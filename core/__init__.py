"""Shared infrastructure used by every agent.

    llm_client      provider-agnostic LLM calls
    schemas         Pydantic contracts at every LLM boundary
    app_context     config + app inventory loading
    usage_ledger    per-story token and cost accounting
    board_status    board column automation
"""
