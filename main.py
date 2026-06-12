import sys
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from src.api import Router
from src.api import Metrics
from src.utils.LogSetup import get_logger

logger = get_logger()

app = FastAPI(title='AtlasCare', version='2.0.0')

# ==========================================
# MIDDLEWARE
# ==========================================
app.add_middleware(
    CORSMiddleware, 
    allow_origins=['*'],               # In production, replace with specific origins 
    allow_credentials=True,            # Allow cookies and authorization headers
    allow_methods=['*'],               # Allow all HTTP methods (GET, POST, PUT, DELETE)
    allow_headers=['*']                # Allow all headers
)

app.include_router(Router.router)
app.include_router(Metrics.metrics)


# ==========================================
# GLOBAL ERROR HANDLING
# ==========================================
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Purpose: Catches any unhandled backend exceptions globally to prevent raw errors from breaking the React UI.
    Args:
        request (Request): The incoming FastAPI request.
        exc (Exception): The unhandled exception that was raised.
    Returns: JSONResponse with a clean, user-friendly 500 error message matching the expected frontend schema.
    Raises: None
    """
    logger.error(f"Global unhandled exception at {request.url}: {exc}", exc_info=True)
    
    # Returning a structure that the frontend can safely render as a chat bubble
    return JSONResponse(
        status_code=500,
        content={
            "response": "I am currently experiencing technical difficulties connecting to the Acme Retail servers. Please try again in a moment.",
            "escalated": False,
            "journey": "System Error"
        }
    )

if __name__ == "__main__":
    try:
        # 2. Start the FastAPI backend on the main thread
        logger.info("⚡ Starting the FastAPI Backend Server on port 8080...")
        
        # reload=False is required here to prevent subprocess duplication 
        uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
        
    except Exception as e:
        logger.critical(f"Critical failure during application startup: {e}", exc_info=True)
        sys.exit(1)