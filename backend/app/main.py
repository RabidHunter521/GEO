from fastapi import FastAPI
from app.api.v1.router import router

app = FastAPI(title="SeenBy API", version="0.1.0")
app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok"}
