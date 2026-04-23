from app.agents.schemas import RequirementDoc


def merge_human_feedback(raw_requirement: str, feedback: str) -> str:
    return f"{raw_requirement}\n\n[人工补充]\n{feedback}"


def requirement_summary_text(requirement_doc: RequirementDoc) -> str:
    return f"{requirement_doc.project_name}: {requirement_doc.summary}"
