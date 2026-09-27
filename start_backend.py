"""
Start the Incident Commander backend on port 8001.
Usage:  python start_backend.py
Set GROQ_API_KEY in environment or pass via environment before running.
"""
import os
import sys
import uvicorn

# Key must be set before backend modules are imported by uvicorn
if not os.environ.get("GROQ_API_KEY"):
    print("ERROR: GROQ_API_KEY environment variable is not set.", file=sys.stderr)
    sys.exit(1)

if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8001,
        reload=False,
    )
