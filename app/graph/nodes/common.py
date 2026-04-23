def extract_structured_response(result: dict):
    structured = result.get("structured_response")
    if structured is None:
        raise ValueError("Agent did not return structured_response")
    return structured
