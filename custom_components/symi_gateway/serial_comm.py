"""Serial communication for Symi Gateway."""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Callable, Optional

import serial
import serial.tools.list_ports

from .const import DEFAULT_BAUDRATE, DEFAULT_TIMEOUT
from .protocol import ProtocolFrame, ProtocolHandler

_LOGGER = logging.getLogger(__name__)


class SerialCommunication:
    """Handles serial communication with Symi Gateway."""
    
    def __init__(self, port: str, baudrate: int = DEFAULT_BAUDRATE):
        """Initialize serial communication."""
        self.port = port
        self.baudrate = baudrate
        self.timeout = DEFAULT_TIMEOUT
        
        self.serial_port: Optional[serial.Serial] = None
        self.is_running = False
        self.read_thread: Optional[threading.Thread] = None
        
        self.protocol_handler = ProtocolHandler()
        self.frame_callbacks: list[Callable[[ProtocolFrame], None]] = []
        self._lock = threading.Lock()
    
    @property
    def is_connected(self) -> bool:
        """Check if serial port is connected."""
        return (
            self.serial_port is not None 
            and self.serial_port.is_open 
            and self.is_running
        )
    
    def add_frame_callback(self, callback: Callable[[ProtocolFrame], None]) -> None:
        """Add a callback for received frames."""
        with self._lock:
            self.frame_callbacks.append(callback)
    
    def remove_frame_callback(self, callback: Callable[[ProtocolFrame], None]) -> None:
        """Remove a frame callback."""
        with self._lock:
            if callback in self.frame_callbacks:
                self.frame_callbacks.remove(callback)
    
    async def async_connect(self) -> bool:
        """Connect to serial port asynchronously."""
        return await asyncio.get_event_loop().run_in_executor(None, self._connect)
    
    def _connect(self) -> bool:
        """Connect to serial port."""
        try:
            _LOGGER.info("🔌 Connecting to serial port %s at %d baud", self.port, self.baudrate)
            
            self.serial_port = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False,
            )
            
            if self.serial_port.is_open:
                _LOGGER.info("✅ Successfully connected to serial port %s", self.port)
                _LOGGER.info("Serial port settings: baudrate=%d, timeout=%.1f", 
                           self.baudrate, self.timeout)
                
                self.is_running = True
                self.read_thread = threading.Thread(target=self._read_loop, daemon=True)
                self.read_thread.start()
                _LOGGER.info("✅ Serial read thread started")
                return True
            else:
                _LOGGER.error("❌ Failed to open serial port %s", self.port)
                return False
                
        except serial.SerialException as err:
            _LOGGER.error("❌ Serial connection error: %s", err)
            _LOGGER.error("   Port: %s", self.port)
            _LOGGER.error("   Baudrate: %d", self.baudrate)
            _LOGGER.error("   Please check:")
            _LOGGER.error("     - Device is connected and powered on")
            _LOGGER.error("     - Port path is correct")
            _LOGGER.error("     - No other program is using the port")
            return False
        except Exception as err:
            _LOGGER.error("❌ Unexpected error connecting to serial port: %s", err)
            _LOGGER.error("   Port: %s", self.port)
            return False
    
    async def async_disconnect(self) -> None:
        """Disconnect from serial port asynchronously."""
        await asyncio.get_event_loop().run_in_executor(None, self._disconnect)
    
    def _disconnect(self) -> None:
        """Disconnect from serial port."""
        self.is_running = False
        
        if self.read_thread and self.read_thread.is_alive():
            self.read_thread.join(timeout=2.0)
        
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
            _LOGGER.info("🔌 Disconnected from serial port %s", self.port)
        
        self.protocol_handler.clear_buffer()
    
    def _read_loop(self) -> None:
        """Read data from serial port in a separate thread."""
        _LOGGER.debug("👂 Starting serial read loop")
        
        while self.is_running and self.serial_port and self.serial_port.is_open:
            try:
                if self.serial_port.in_waiting > 0:
                    data = self.serial_port.read(self.serial_port.in_waiting)
                    if data:
                        _LOGGER.debug("📥 Received %d bytes: %s", len(data), data.hex().upper())
                        self._process_received_data(data)
                else:
                    time.sleep(0.01)
                    
            except serial.SerialException as err:
                _LOGGER.error("❌ Serial read error: %s", err)
                break
            except Exception as err:
                _LOGGER.error("❌ Unexpected read error: %s", err)
                break
        
        _LOGGER.debug("🛑 Serial read loop ended")
    
    def _process_received_data(self, data: bytes) -> None:
        """Process received data and parse frames."""
        frames = self.protocol_handler.add_data(data)
        
        for frame in frames:
            _LOGGER.debug("📦 Parsed frame: opcode=0x%02X, status=%s, length=%d", 
                         frame.opcode, frame.status, frame.length)
            
            # Notify callbacks
            with self._lock:
                for callback in self.frame_callbacks:
                    try:
                        callback(frame)
                    except Exception as err:
                        _LOGGER.error("❌ Error in frame callback: %s", err)
    
    async def async_send_frame(self, frame_data: bytes) -> bool:
        """Send frame data asynchronously."""
        return await asyncio.get_event_loop().run_in_executor(None, self._send_frame, frame_data)
    
    def _send_frame(self, frame_data: bytes) -> bool:
        """Send frame data."""
        if not self.is_connected:
            _LOGGER.error("❌ Cannot send frame: serial port not connected")
            return False
        
        try:
            _LOGGER.debug("📤 Sending frame: %s", frame_data.hex().upper())
            
            bytes_written = self.serial_port.write(frame_data)
            self.serial_port.flush()
            
            _LOGGER.debug("✅ Sent %d bytes successfully", bytes_written)
            return True
            
        except serial.SerialException as err:
            _LOGGER.error("❌ Serial send error: %s", err)
            return False
        except Exception as err:
            _LOGGER.error("❌ Unexpected send error: %s", err)
            return False
    
    @staticmethod
    def get_available_ports() -> list[str]:
        """Get list of available serial ports."""
        ports = []
        try:
            for port in serial.tools.list_ports.comports():
                ports.append(port.device)
                _LOGGER.debug("Found serial port: %s - %s", port.device, port.description)
        except Exception as err:
            _LOGGER.error("❌ Error listing serial ports: %s", err)
        
        return ports
    
    def get_status(self) -> dict[str, any]:
        """Get detailed serial connection status."""
        return {
            "port": self.port,
            "baudrate": self.baudrate,
            "timeout": self.timeout,
            "is_connected": self.is_connected,
            "serial_port_open": self.serial_port.is_open if self.serial_port else False,
            "is_running": self.is_running,
            "read_thread_alive": self.read_thread.is_alive() if self.read_thread else False,
            "buffer_size": len(self.protocol_handler.buffer),
        }
