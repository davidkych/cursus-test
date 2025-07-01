from fastapi import APIRouter

router = APIRouter()

@router.get("/api/hello")
def say_hello():
    return {"message": "Hello, World!"}
