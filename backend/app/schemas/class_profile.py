from pydantic import BaseModel, ConfigDict, Field


class ClassProfileBase(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    grade: int = Field(ge=1, le=6)
    student_count: int = Field(ge=1, le=100)
    province: str
    learning_level: str
    activity_level: str
    cooperation: str
    pitch_level: str
    rhythm_level: str
    theory_level: str
    preferred_method: str
    common_problems: str = ""
    teacher_notes: str = ""


class ClassProfileCreate(ClassProfileBase):
    pass


class ClassProfileUpdate(ClassProfileBase):
    pass


class ClassProfileRead(ClassProfileBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
