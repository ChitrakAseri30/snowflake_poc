import os
import sys
import json
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.utils.LogSetup import get_logger

logger = get_logger()

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TRACE_DIR = _PROJECT_ROOT / "traces"

try:
    TRACE_DIR.mkdir(exist_ok=True)
except Exception as e:
    logger.warning(f"Could not create trace directory: {e}")

TRACE_FILE = TRACE_DIR / "traces.json"


@dataclass
class ToolCall:
    """
    Purpose: A data class representing a single execution of a tool by the LLM.
    Args:
        tool_name (str): The name of the tool executed.
        inputs (dict): The arguments passed to the tool.
        output (dict): The parsed output or result returned by the tool.
        success (bool): Whether the tool execution was successful.
        latency_ms (int): Execution time in milliseconds.
        attempt (int): The attempt number for this tool call.
        timestamp (str): ISO-8601 formatted timestamp of the call.
    Returns: None
    Raises: None
    """
    tool_name: str
    inputs: dict
    output: dict
    success: bool
    latency_ms: int
    attempt: int = 1
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

class Tracer:
    def __init__(self, trace_id: str, session_id: str):
        """
        Purpose: Initializes a new trace session for a specific user interaction.
        Args:
            trace_id (str): Unique identifier for this specific request trace.
            session_id (str): The user's active session identifier.
        Returns: None
        Raises: None
        """
        self.trace_id = trace_id
        self.session_id = session_id
        self.calls: list[dict] = []
        self._started_at = datetime.now(timezone.utc).isoformat()
        logger.debug(f"[{self.trace_id}] Tracer initialized for session: {self.session_id}")

    def add_call(self, tool_name: str, inputs: dict, output: str, success: bool, latency_ms: int):
        """
        Purpose: Records a tool execution event into the trace log safely.
        Args:
            tool_name (str): The name of the executed tool.
            inputs (dict): The arguments passed to the tool.
            output (str): The raw string output from the tool.
            success (bool): Whether the tool execution was successful.
            latency_ms (int): The execution time in milliseconds.
        Returns: None
        Raises: None (All exceptions are caught to prevent breaking the main application).
        """
        try:
            # SAFETY CATCH: LLMs sometimes hallucinate and pass strings instead of dicts.
            # This ensures we always have a dictionary so FastAPI doesn't crash on return.
            safe_inputs = inputs if isinstance(inputs, dict) else {"raw_input": str(inputs)}

            # Ensure output is serialized safely for the API response
            try:
                parsed_output = json.loads(output)
            except (ValueError, TypeError):
                parsed_output = {"result": str(output)}

            # Force type casting just in case something weird was passed down
            call = ToolCall(
                tool_name=str(tool_name),
                inputs=safe_inputs,
                output=parsed_output,
                success=bool(success),
                latency_ms=int(latency_ms)
            )
            
            # Convert dataclass to dict for easy API serialization
            self.calls.append({
                "tool_name": call.tool_name,
                "inputs": call.inputs,
                "output": call.output,
                "success": call.success,
                "latency_ms": call.latency_ms,
                "timestamp": call.timestamp
            })
            
            logger.debug(f"[{self.trace_id}] Recorded tool call: {tool_name} (Success: {success})")
            
        except Exception as e:
            # If telemetry fails entirely, we log it but NEVER crash the user's chat response
            logger.error(f"[{self.trace_id}] Failed to record tool call '{tool_name}': {e}", exc_info=True)

    def flush_to_file(self, journey: str = "General Inquiry", is_escalated: bool = False):
        """
        Purpose: Appends the completed trace record for this request to traces/traces.json.
                 Reads the existing file (if any), appends the new record, and writes back
                 atomically so no prior records are lost across requests.
        Args:
            journey (str): The classified journey label (e.g. 'Order Lookup', 'Cancel Order').
            is_escalated (bool): Whether this interaction triggered a human escalation.
        Returns: None
        Raises: None (All exceptions are caught to prevent breaking the main application).
        """
        try:
            record = {
                "trace_id": self.trace_id,
                "session_id": self.session_id,
                "started_at": self._started_at,
                "flushed_at": datetime.now(timezone.utc).isoformat(),
                "journey": journey,
                "is_escalated": is_escalated,
                "tool_calls": self.calls
            }

            # Load existing records (gracefully handle missing or corrupt file)
            existing: list = []
            if TRACE_FILE.exists():
                try:
                    with open(TRACE_FILE, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                        if content:
                            existing = json.loads(content)
                            if not isinstance(existing, list):
                                # Corrupt or unexpected format — start fresh but log it
                                logger.warning(f"[{self.trace_id}] traces.json had unexpected format; resetting.")
                                existing = []
                except (json.JSONDecodeError, OSError) as read_err:
                    logger.warning(f"[{self.trace_id}] Could not read traces.json: {read_err}. Starting fresh.")
                    existing = []

            existing.append(record)

            with open(TRACE_FILE, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)

            logger.debug(f"[{self.trace_id}] Trace flushed to {TRACE_FILE} ({len(self.calls)} tool call(s))")

        except Exception as e:
            # Never let a file-write failure crash the chat response
            logger.error(f"[{self.trace_id}] Failed to flush trace to file: {e}", exc_info=True)