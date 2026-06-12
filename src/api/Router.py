import sys
import os
import uuid
import time
import asyncio
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import src.utils.Constants as CONSTANT
from src.agent.Graph import run_agent
from src.agent.Tracer import Tracer
from src.api.Model import QueryRequest, TraceModel, QueryResponse
from src.api.Middleware import verify_jwt
from src.utils.LogSetup import get_logger

logger = get_logger()

router = APIRouter(
    prefix = "",
    tags = ["Backend APIs"],
    responses = {404: {"description": "Not found"}}
)

# Metrics with p95/p99 support
_metrics = {'total_requests':0,'total_latency_ms':0, 'latency_samples':[],'tool_errors':0, 'escalations':0,'journey_counts':{}}

# Rate limiter
_rate_store = defaultdict(list)


def _check_rate(session_id: str) -> bool:
    """
    Purpose: Enforces a rate limit of 10 requests per minute per session.
    Args:
        session_id (str): The unique session identifier.
    Returns: bool indicating whether the request is allowed (True) or rate-limited (False).
    Raises: None
    """
    try:
        now = time.time()
        window = [t for t in _rate_store[session_id] if now-t < 60]
        _rate_store[session_id] = window
        if len(window) >= 10: 
            logger.warning(f"Rate limit exceeded for session: {session_id}")
            return False
        _rate_store[session_id].append(now)
        return True
    except Exception as e:
        # If rate limiting fails, we fail open so users aren't blocked by internal bugs
        logger.error(f"Error in rate limiter for {session_id}: {e}", exc_info=True)
        return True


# ============================================
# API 1: Health
# ============================================
@router.get("/health")
def root_health_check():
    """
    Purpose: Root health check endpoint to verify backend status.
    Args: None
    Returns: dict containing the health status.
    Raises: None
    """
    logger.debug("Health check ping received.")
    return {"status": "healthy"}


# ============================================
# API 2: Query
# ============================================
@router.post('/query', response_model=QueryResponse)
async def query(req: QueryRequest, token: dict = Depends(verify_jwt)) -> QueryResponse:
    """
    Purpose: Main endpoint to process user messages, enforce timeouts, and trigger the agent loop.
    Args:
        req (QueryRequest): The incoming payload containing the message and session_id.
        token (dict): The verified Auth0 JWT payload injected by dependencies.
    Returns: QueryResponse containing the LLM text response and the full telemetry trace.
    Raises: None (All exceptions are caught and returned as user-friendly chat responses).
    """

    trace_id = f'trc-{uuid.uuid4().hex[:12]}'
    t0 = time.time()

    logger.info(f"[{trace_id}] Incoming query from session {req.session_id}: '{req.message}'")

    # Rate Limit Check
    if not _check_rate(req.session_id):
        return QueryResponse(
            response="You're sending messages a bit too quickly! Please wait a moment and try asking again.",
            trace=TraceModel(trace_id=trace_id, session_id=req.session_id, latency_ms=0, tool_calls=[])
        )
    
    tracer = Tracer(trace_id=trace_id, session_id=req.session_id)
    
    try:
        # Extract the secure identity from the Auth0 token
        user_email = token.get("https://atlascare.com/email", "unknown@acmeretail.com")
        logger.debug(f"[{trace_id}] Authenticated user: {user_email}")
        
        # Enforcing the 15-second timeout requirement
        result = await asyncio.wait_for(
            run_agent(req.message, req.session_id, user_email, tracer), 
            timeout=15.0
        )
        
        lat = int((time.time()-t0)*1000)

        try:
            m = _metrics
            m['total_requests'] += 1
            m['total_latency_ms'] += lat
            m['latency_samples'] = (m['latency_samples'] + [lat])[-1000:]
            
            if result.get('escalated'): 
                m['escalations'] += 1
                
            m['tool_errors'] += sum(1 for c in tracer.calls if not c.get('success', True))
            
            j = result.get('journey', 'unknown')
            m['journey_counts'][j] = m['journey_counts'].get(j, 0) + 1
        except Exception as metric_err:
            logger.warning(f"[{trace_id}] Failed to update memory metrics: {metric_err}", exc_info=True)
            
        logger.info(f"[{trace_id}] Query processed successfully in {lat}ms. Journey: {result.get('journey')}")
        
        return QueryResponse(
            response=result['response'],
            trace=TraceModel(
                trace_id=trace_id, 
                session_id=req.session_id,
                latency_ms=lat, 
                tool_calls=tracer.calls
            )
        )
        
    except asyncio.TimeoutError:
        lat = int((time.time() - t0) * 1000)
        logger.warning(f"[{trace_id}] Request timed out after 15s")
        # Graceful UI degradation
        return QueryResponse(
            response="I'm sorry, that request took a little too long for me to process. Could you please try asking again?",
            trace=TraceModel(trace_id=trace_id, session_id=req.session_id, latency_ms=lat, tool_calls=tracer.calls)
        )
        
    except Exception as e:
        lat = int((time.time() - t0) * 1000)
        logger.error(f"[{trace_id}] Unexpected agent error: {e}", exc_info=True)
        # Graceful UI degradation
        return QueryResponse(
            response="I encountered an unexpected technical issue while processing your request. Please try again or contact support if the issue persists.",
            trace=TraceModel(trace_id=trace_id, session_id=req.session_id, latency_ms=lat, tool_calls=tracer.calls)
        )