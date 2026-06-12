from pydantic import BaseModel

class QueryRequest(BaseModel):
    message: str
    session_id: str

class TraceModel(BaseModel):
    trace_id: str
    session_id: str
    latency_ms: int
    tool_calls: list

class QueryResponse(BaseModel):
    response: str
    trace: TraceModel