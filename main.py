from fastapi import FastAPI
from src.api.routes import router
import structlog

# Setup structlog for JSON formatting in production
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)

app = FastAPI(
    title="Document Intelligence Pipeline MVP",
    description="Purchase Order PDF -> Structured JSON Service",
    version="1.0.0"
)

app.include_router(router)

@app.get("/health")
def health_check():
    return {"status": "ok"}
