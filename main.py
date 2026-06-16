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

from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

app = FastAPI(
    title="Document Intelligence Pipeline MVP",
    description="Purchase Order PDF -> Structured JSON Service",
    version="1.0.0"
)

# Serve the static files
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", include_in_schema=False)
def index():
    return RedirectResponse(url="/static/index.html")

app.include_router(router)

@app.get("/health")
def health_check():
    return {"status": "ok"}
