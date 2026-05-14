"""
FastAPI REST API for RWA calculations.
"""

from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from .engine import RwaEngine
from .models import RwaCalculationRequest, RwaCalculationResponse


# Create FastAPI application
app = FastAPI(
    title="Basel III RWA Calculator API",
    description="REST API for calculating Risk-Weighted Assets according to Basel III final reforms",
    version="0.1.0"
)

# Global engine instance
_engine: Optional[RwaEngine] = None


def get_engine() -> RwaEngine:
    """Get or create the RWA engine instance."""
    global _engine
    if _engine is None:
        _engine = RwaEngine()
    return _engine


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "Basel III RWA Calculator API",
        "version": "0.1.0",
        "status": "operational",
        "endpoints": {
            "calculate": "/api/v1/calculate",
            "health": "/health",
            "reference_data": "/api/v1/reference-data"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        engine = get_engine()
        ref_data_info = engine.get_reference_data_info()
        return {
            "status": "healthy",
            "reference_data_loaded": ref_data_info["nccr_grades_loaded"] > 0,
            "nccr_grades_count": ref_data_info["nccr_grades_loaded"]
        }
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e)
            }
        )


@app.get("/api/v1/reference-data")
async def get_reference_data():
    """Get information about loaded reference data."""
    try:
        engine = get_engine()
        return engine.get_reference_data_info()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/calculate", response_model=RwaCalculationResponse)
async def calculate_rwa(request: RwaCalculationRequest) -> RwaCalculationResponse:
    """
    Calculate RWA for a portfolio of exposures.
    
    Args:
        request: RWA calculation request with core and country info
    
    Returns:
        RWA calculation response with results and summary
    """
    try:
        engine = get_engine()
        response = engine.calculate(request)
        return response
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Calculation error: {str(e)}"
        )


@app.post("/api/v1/calculate-with-trace")
async def calculate_rwa_with_trace(request: RwaCalculationRequest):
    """
    Calculate RWA with detailed calculation traces.
    
    Args:
        request: RWA calculation request with core and country info
    
    Returns:
        Detailed calculation results including step-by-step traces
    """
    try:
        engine = get_engine()
        result = engine.calculate_with_trace(
            request.core_info,
            request.country_info
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Calculation error: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

# Made with Bob
