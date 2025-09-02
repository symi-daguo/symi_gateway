"""Symi Gateway Protocol Implementation."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from .const import PROTOCOL_HEADER, MIN_FRAME_LENGTH

_LOGGER = logging.getLogger(__name__)


@dataclass
class ProtocolFrame:
    """Represents a protocol frame."""

    header: int
    opcode: int
    length: int
    payload: bytes
    checksum: int
    status: Optional[int] = None  # Only for response frames

    @property
    def is_response(self) -> bool:
        """Check if this is a response frame."""
        return self.opcode >= 0x81

    @property
    def is_event(self) -> bool:
        """Check if this is an event frame."""
        return self.opcode == 0x80 or (self.opcode == 0x90 and self.status in [0x02, 0x03, 0x04, 0x05, 0x06])  

    @property
    def is_scan_response(self) -> bool:
        """Check if this is a scan discovery response."""
        return self.opcode == 0x90 and self.status == 0x00

    @property
    def is_device_discovery(self) -> bool:
        """Check if this is a device discovery event."""
        return self.opcode == 0x90 and self.status == 0x02

    @property
    def is_device_status_event(self) -> bool:
        """Check if this is a device status event."""
        return self.opcode == 0x80 and self.status == 0x06


class ProtocolHandler:
    """Handles Symi Gateway protocol parsing and frame building."""

    def __init__(self):
        """Initialize protocol handler."""
        self.buffer = bytearray()

    def calculate_checksum(self, data: bytes) -> int:
        """Calculate XOR checksum."""
        checksum = 0
        for byte in data:
            checksum ^= byte
        return checksum

    def build_frame(self, opcode: int, data: bytes = b'') -> bytes:
        """Build a protocol frame for sending."""
        # Send format: Head + Opcode + ParamLength + ParamData + Check
        header = PROTOCOL_HEADER
        length = len(data)

        frame_without_checksum = bytes([header, opcode, length]) + data
        checksum = self.calculate_checksum(frame_without_checksum)

        return frame_without_checksum + bytes([checksum])

    def parse_frame(self, data: bytes) -> Optional[ProtocolFrame]:
        """Parse a single protocol frame."""
        if len(data) < MIN_FRAME_LENGTH:
            return None

        header = data[0]
        if header != PROTOCOL_HEADER:
            return None

        opcode = data[1]

        # Determine frame format based on opcode
        if opcode >= 0x81:  # Response format
            # Response format: Head + Opcode + Status + ParamLength + ParamData + Check
            if len(data) < 5:  # Minimum response frame length
                return None

            status = data[2]
            param_length = data[3]

            expected_length = 5 + param_length

            if len(data) != expected_length:
                _LOGGER.debug("Response frame length mismatch: expected %d, got %d", expected_length, len(data))
                return None

            # Extract payload and checksum
            payload = data[4:4+param_length] if param_length > 0 else b''
            checksum = data[4+param_length]

            # Verify checksum
            calculated_checksum = self.calculate_checksum(data[:-1])

            if checksum != calculated_checksum:
                _LOGGER.debug("Response checksum mismatch: expected 0x%02X, got 0x%02X", calculated_checksum, checksum)
                return None

            return ProtocolFrame(header, opcode, param_length, payload, checksum, status)

        else:  # Send format
            # Send format: Head + Opcode + ParamLength + ParamData + Check
            param_length = data[2]

            expected_length = 4 + param_length

            if len(data) != expected_length:
                _LOGGER.debug("Send frame length mismatch: expected %d, got %d", expected_length, len(data))   
                return None

            # Extract payload and checksum
            payload = data[3:3+param_length] if param_length > 0 else b''
            checksum = data[3+param_length]

            # Verify checksum
            calculated_checksum = self.calculate_checksum(data[:-1])

            if checksum != calculated_checksum:
                _LOGGER.debug("Send checksum mismatch: expected 0x%02X, got 0x%02X", calculated_checksum, checksum)
                return None

            return ProtocolFrame(header, opcode, param_length, payload, checksum)

    def add_data(self, data: bytes) -> list[ProtocolFrame]:
        """Add data to buffer and parse complete frames."""
        self.buffer.extend(data)
        frames = []

        while len(self.buffer) >= MIN_FRAME_LENGTH:
            # Look for frame header
            header_index = -1
            for i in range(len(self.buffer)):
                if self.buffer[i] == PROTOCOL_HEADER:
                    header_index = i
                    break

            if header_index == -1:
                # No header found, clear buffer
                self.buffer.clear()
                break

            if header_index > 0:
                # Remove data before header
                self.buffer = self.buffer[header_index:]

            # Check if we have enough data for opcode and length field
            if len(self.buffer) < 3:
                break

            opcode = self.buffer[1]

            # Determine frame format and calculate total length
            if opcode >= 0x81:  # Response format
                if len(self.buffer) < 4:  # Need at least 4 bytes to read ParamLength
                    break

                param_length = self.buffer[3]  # 4th byte is ParamLength
                total_frame_length = 5 + param_length

            else:  # Send format
                param_length = self.buffer[2]  # 3rd byte is ParamLength
                total_frame_length = 4 + param_length

            # Check if we have complete frame
            if len(self.buffer) < total_frame_length:
                break

            # Extract frame data
            frame_data = bytes(self.buffer[:total_frame_length])

            # Parse frame
            frame = self.parse_frame(frame_data)
            if frame:
                frames.append(frame)
                _LOGGER.debug("Parsed frame: opcode=0x%02X, length=%d", frame.opcode, frame.length)
            else:
                _LOGGER.debug("Failed to parse frame: %s", frame_data.hex())

            # Remove processed frame from buffer
            self.buffer = self.buffer[total_frame_length:]

        return frames

    def clear_buffer(self) -> None:
        """Clear the internal buffer."""
        self.buffer.clear()


def build_read_device_list_frame() -> bytes:
    """Build read device list frame."""
    handler = ProtocolHandler()
    return handler.build_frame(0x12)  # OP_READ_DEVICE_LIST


def build_device_control_frame(network_addr: int, msg_type: int, param: bytes = b'') -> bytes:
    """Build device control frame."""
    handler = ProtocolHandler()
    # 设备控制命令: 地址(2字节) + msg_type(1字节) + 参数
    payload = network_addr.to_bytes(2, 'little') + bytes([msg_type]) + param
    return handler.build_frame(0x30, payload)  # OP_DEVICE_CONTROL
