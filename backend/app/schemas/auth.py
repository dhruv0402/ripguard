from pydantic import BaseModel, EmailStr, ConfigDict
import uuid


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr



class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
