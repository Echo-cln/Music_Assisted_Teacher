from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)
    password_confirm: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=5, max_length=160)
    verification_code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    school: str = Field(default="", max_length=160)


class LoginRequest(BaseModel):
    account: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=1, max_length=128)


class TeacherRead(BaseModel):
    id: int
    username: str
    display_name: str
    email: str | None
    school: str
    role: str
    verification_status: str


class VerificationRequest(BaseModel):
    email: str = Field(min_length=5, max_length=160)
