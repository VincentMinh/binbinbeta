from pydantic import BaseModel

class VerifyPasswordPayload(BaseModel):
    username: str
    password: str