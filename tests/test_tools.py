from app.tools.requirement_tools import detect_requirement_gaps, extract_plain_text_requirement


def test_extract_plain_text_requirement():
    assert extract_plain_text_requirement.invoke({"raw_text": "  hello  "}) == "hello"


def test_detect_requirement_gaps():
    gaps = detect_requirement_gaps.invoke({"raw_text": "做一个商城系统"})
    assert isinstance(gaps, list)
    assert len(gaps) >= 1
