"""Liquidsoap Unix socket client with heartbeat and reconnection."""

import asyncio

from core.config import LIQUIDSOAP_SOCKET

_reader: asyncio.StreamReader | None = None
_writer: asyncio.StreamWriter | None = None
_lock = asyncio.Lock()


async def _connect():
    global _reader, _writer
    try:
        _reader, _writer = await asyncio.open_unix_connection(LIQUIDSOAP_SOCKET)
    except Exception as e:
        _reader, _writer = None, None
        print(f"[liquidsoap] Connection failed: {e}")


async def _ensure_connected():
    global _reader, _writer
    if _writer is None or _writer.is_closing():
        await _connect()


async def send_command(cmd: str) -> str | None:
    """Send a command to Liquidsoap and return the response."""
    async with _lock:
        await _ensure_connected()
        if _writer is None:
            return None

        try:
            _writer.write(f"{cmd}\n".encode())
            await _writer.drain()

            # Read until END marker
            lines = []
            while True:
                line = await asyncio.wait_for(_reader.readline(), timeout=5.0)
                decoded = line.decode().strip()
                if decoded == "END":
                    break
                lines.append(decoded)

            return "\n".join(lines)
        except Exception as e:
            print(f"[liquidsoap] Command error: {e}")
            # Force reconnect next time
            try:
                _writer.close()
            except Exception:
                pass
            _writer = None
            _reader = None
            return None


async def push_break(audio_path: str) -> bool:
    """Push a break audio file to the breaks queue."""
    result = await send_command(f"breaks.push {audio_path}")
    return result is not None


async def push_sting(audio_path: str) -> bool:
    """Push a sting audio file to the stings queue (interrupts immediately)."""
    result = await send_command(f"stings.push {audio_path}")
    return result is not None


async def reset_counter() -> bool:
    """Reset the track counter to 0."""
    result = await send_command("hermes.reset_counter")
    return result is not None


async def get_track_count() -> int | None:
    """Get current track count."""
    result = await send_command("hermes.track_count")
    if result is not None:
        try:
            return int(result.strip())
        except ValueError:
            pass
    return None


async def skip_track() -> bool:
    """Skip current track."""
    result = await send_command("hermes.skip")
    return result is not None


async def heartbeat() -> bool:
    """Check if Liquidsoap is responsive."""
    result = await send_command("version")
    return result is not None


async def close():
    global _reader, _writer
    if _writer is not None:
        try:
            _writer.close()
            await _writer.wait_closed()
        except Exception:
            pass
        _writer = None
        _reader = None
