"""Offline Bengali speech fallback for browsers without an installed voice."""
import asyncio
import os
import shutil
from pathlib import Path


def command() -> list[str]:
    executable = os.environ.get("CTC_ESPEAK") or shutil.which("espeak-ng")
    if executable:
        return [executable]
    local = Path.home() / ".local/lib/ctc-speech-tools/usr"
    if (local / "bin/espeak-ng").exists():
        return [str(local / "bin/espeak-ng"), f"--path={local / 'lib/x86_64-linux-gnu'}"]
    raise RuntimeError("Install espeak-ng for offline Bengali speech, or install a Bengali browser voice")


async def synthesize(text: str) -> bytes:
    cmd = command()
    env = os.environ.copy()
    local_lib = Path.home() / ".local/lib/ctc-speech-tools/usr/lib/x86_64-linux-gnu"
    if "ctc-speech-tools" in cmd[0]:
        env["LD_LIBRARY_PATH"] = str(local_lib) + ":" + env.get("LD_LIBRARY_PATH", "")
    process = await asyncio.create_subprocess_exec(
        *cmd, "-v", "bn", "-s", "155", "--stdout", "--stdin",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE, env=env,
    )
    try:
        audio, error = await asyncio.wait_for(process.communicate(text.encode()), timeout=20)
        if process.returncode:
            raise RuntimeError(error.decode(errors="replace")[:200])
        return audio
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
