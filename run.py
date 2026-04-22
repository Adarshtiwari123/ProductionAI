"""
run.py — Clean server launcher for Windows.
Runs uvicorn programmatically to avoid PowerShell's
NativeCommandError false-alarm on stderr output.
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
