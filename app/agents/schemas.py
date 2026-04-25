from typing import Any

from pydantic import BaseModel, Field, model_validator


class RequirementDoc(BaseModel):
    project_name: str = Field(description="项目名称")
    summary: str = Field(description="需求摘要")
    roles: list[str] = Field(default_factory=list)
    modules: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)


class FeasibilityReport(BaseModel):
    feasible: bool
    complexity: str
    risks: list[str] = Field(default_factory=list)
    missing_info: list[str] = Field(default_factory=list)
    mvp_scope: list[str] = Field(default_factory=list)


class ArchitectureModule(BaseModel):
    name: str
    responsibilities: list[str] = Field(default_factory=list)
    tasks: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_responsibility(cls, data: Any):
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        if "responsibilities" not in normalized and "responsibility" in normalized:
            responsibility = normalized.pop("responsibility")
            if isinstance(responsibility, list):
                normalized["responsibilities"] = [str(item) for item in responsibility]
            elif responsibility:
                normalized["responsibilities"] = [str(responsibility)]
        return normalized


class ArchitecturePlan(BaseModel):
    architecture_style: str
    backend: list[str] = Field(default_factory=list)
    frontend: list[str] = Field(default_factory=list)
    modules: list[ArchitectureModule] = Field(default_factory=list)
    data_entities: list[str] = Field(default_factory=list)


class TaskItem(BaseModel):
    title: str
    description: str
    priority: str
    depends_on: list[str] = Field(default_factory=list)
    owner_role: str


class PlannerOutput(BaseModel):
    milestones: list[str] = Field(default_factory=list)
    tasks: list[TaskItem] = Field(default_factory=list)


class PromptTask(BaseModel):
    task_title: str
    coding_prompt: str
    test_prompt: str


class PromptPackOutput(BaseModel):
    prompts: list[PromptTask] = Field(default_factory=list)


class ReviewReport(BaseModel):
    passed: bool
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
