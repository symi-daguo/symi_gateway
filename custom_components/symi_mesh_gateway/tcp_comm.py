"""TCP communication for Symi Gateway."""
from __future__ import annotations

import asyncio
import logging
from typing import Callable, Optional

from .const import DEFAULT_TIMEOUT
from .protocol import ProtocolFrame, ProtocolHandler

_LOGGER = logging.getLogger(__name__)


class TCPCommunication:
    """Handles TCP communication with Symi Gateway."""

    def __init__(self, host: str, port: int):
        """Initialize TCP communication."""
        self.host = host
        self.port = port
        self.timeout = DEFAULT_TIMEOUT

        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.is_running = False
        self.read_task: Optional[asyncio.Task] = None

        self.protocol_handler = ProtocolHandler()
        self.frame_callbacks: list[Callable[[ProtocolFrame], None]] = []
        self._lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        """Check if TCP connection is established."""
        return (
            self.writer is not None
            and not self.writer.is_closing()
            and self.is_running
        )

    def add_frame_callback(self, callback: Callable[[ProtocolFrame], None]) -> None:
        """Add a callback for received frames."""
        self.frame_callbacks.append(callback)

    def remove_frame_callback(self, callback: Callable[[ProtocolFrame], None]) -> None:
        """Remove a frame callback."""
        if callback in self.frame_callbacks:
            self.frame_callbacks.remove(callback)

    async def async_connect(self) -> bool:
        """Connect to TCP server."""
        try:
            _LOGGER.info("🔌 Connecting to TCP server %s:%d", self.host, self.port)

            # Create connection with timeout
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.timeout
            )

            _LOGGER.info("✅ Successfully connected to TCP server %s:%d", self.host, self.port)

            self.is_running = True
            self.read_task = asyncio.create_task(self._read_loop())
            _LOGGER.info("✅ TCP read task started")
            return True

        except asyncio.TimeoutError:
            _LOGGER.error("❌ TCP connection timeout: %s:%d", self.host, self.port)
            return False
        except ConnectionRefusedError:
            _LOGGER.error("❌ TCP connection refused: %s:%d", self.host, self.port)
            _LOGGER.error("   Please check:")
            _LOGGER.error("     - Gateway device is powered on")
            _LOGGER.error("     - Network connectivity")
            _LOGGER.error("     - Host and port are correct")
            return False
        except Exception as err:
            _LOGGER.error("❌ TCP connection error: %s", err)
            _LOGGER.error("   Host: %s", self.host)
            _LOGGER.error("   Port: %d", self.port)
            return False

    async def async_disconnect(self) -> None:
        """Disconnect from TCP server."""
        self.is_running = False

        if self.read_task and not self.read_task.done():
            self.read_task.cancel()
            try:
                await self.read_task
            except asyncio.CancelledError:
                pass

        if self.writer and not self.writer.is_closing():
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except Exception as err:
                _LOGGER.debug("Error closing TCP writer: %s", err)
            _LOGGER.info("🔌 Disconnected from TCP server %s:%d", self.host, self.port)

        self.protocol_handler.clear_buffer()

    async def _read_loop(self) -> None:
        """Read data from TCP connection in a loop."""
        _LOGGER.debug("👂 Starting TCP read loop")

        while self.is_running and self.reader and not self.reader.at_eof():
            try:
                # Read data with timeout
                data = await asyncio.wait_for(
                    self.reader.read(1024),
                    timeout=1.0
                )

                if data:
                    _LOGGER.debug("📥 Received %d bytes: %s", len(data), data.hex().upper())
                    await self._process_received_data(data)
                else:
                    # Connection closed by remote
                    _LOGGER.warning("⚠️ TCP connection closed by remote")
                    break

            except asyncio.TimeoutError:
                # Normal timeout, continue reading
                continue
            except ConnectionResetError:
                _LOGGER.error("❌ TCP connection reset by peer")
                break
            except Exception as err:
                _LOGGER.error("❌ TCP read error: %s", err)
                break

        _LOGGER.debug("🛑 TCP read loop ended")

    async def _process_received_data(self, data: bytes) -> None:
        """Process received data and parse frames."""
        _LOGGER.warning("📥 TCP RECV: %d bytes: %s", len(data), data.hex().upper())
        frames = self.protocol_handler.add_data(data)

        for frame in frames:
            _LOGGER.warning("📦 PARSED FRAME: opcode=0x%02X, status=%s, length=%d, payload=%s",
                         frame.opcode, frame.status, frame.length, frame.payload.hex().upper() if frame.payload else "")

            # Notify callbacks
            async with self._lock:
                _LOGGER.warning("🔔 Notifying %d frame callbacks", len(self.frame_callbacks))
                for callback in self.frame_callbacks:
                    try:
                        callback(frame)
                    except Exception as err:
                        _LOGGER.error("❌ Error in frame callback: %s", err)

    async def async_send_frame(self, frame_data: bytes) -> bool:
        """Send frame data."""
        if not self.is_connected:
            _LOGGER.error("❌ Cannot send frame: TCP connection not established")
            # Try to reconnect
            _LOGGER.info("🔄 Attempting to reconnect...")
            if await self.async_connect():
                _LOGGER.info("✅ Reconnected successfully")
            else:
                _LOGGER.error("❌ Reconnection failed")
                return False

        try:
            _LOGGER.warning("📤 TCP SEND: %s", frame_data.hex().upper())

            self.writer.write(frame_data)
            await self.writer.drain()

            _LOGGER.warning("✅ TCP SENT: %d bytes successfully", len(frame_data))
            return True

        except ConnectionResetError:
            _LOGGER.error("❌ TCP connection reset during send")
            return False
        except Exception as err:
            _LOGGER.error("❌ TCP send error: %s", err)
            return False
