"""Base converter classes for Symi devices."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..device import SymiDevice

_LOGGER = logging.getLogger(__name__)


class Converter:
    """Base converter class."""
    
    def __init__(self, attr: str, domain: str = None, *, 
                 prop: str = None, parent: str = None, 
                 childs: list = None, **kwargs):
        self.attr = attr
        self.domain = domain
        self.prop = prop or attr
        self.parent = parent
        self.childs = childs or []
        self.device_class = kwargs.get('device_class')
        self.unit_of_measurement = kwargs.get('unit_of_measurement')
        
    def decode(self, device: "SymiDevice", payload: dict, value: Any):
        """Decode device value to HA state."""
        payload[self.attr] = value
        
    def encode(self, device: "SymiDevice", payload: dict, value: Any):
        """Encode HA state to device value."""
        payload[self.prop] = value
        
    def read(self, device: "SymiDevice", payload: dict):
        """Add read request to payload."""
        pass


class BoolConv(Converter):
    """Boolean converter."""
    
    def decode(self, device: "SymiDevice", payload: dict, value: Any):
        if isinstance(value, (int, float)):
            payload[self.attr] = bool(value)
        elif isinstance(value, str):
            payload[self.attr] = value.lower() in ('true', '1', 'on')
        else:
            payload[self.attr] = bool(value)
            
    def encode(self, device: "SymiDevice", payload: dict, value: Any):
        payload[self.prop] = 1 if value else 0


class BrightnessConv(Converter):
    """Brightness converter (0-255 to 0-100)."""
    
    def decode(self, device: "SymiDevice", payload: dict, value: Any):
        if isinstance(value, (int, float)):
            # Convert from device range (0-100) to HA range (0-255)
            payload[self.attr] = int(value * 255 / 100)
        else:
            payload[self.attr] = 0
            
    def encode(self, device: "SymiDevice", payload: dict, value: Any):
        # Convert from HA range (0-255) to device range (0-100)
        payload[self.prop] = int(value * 100 / 255)


class ColorTempConv(Converter):
    """Color temperature converter."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.min_mireds = kwargs.get('min_mireds', 153)  # 6500K
        self.max_mireds = kwargs.get('max_mireds', 500)  # 2000K
    
    def decode(self, device: "SymiDevice", payload: dict, value: Any):
        if isinstance(value, (int, float)):
            # Convert from Kelvin to mireds
            if value > 1000:  # Assume it's Kelvin
                payload[self.attr] = int(1000000 / value)
            else:  # Assume it's already mireds or percentage
                payload[self.attr] = int(value)
        else:
            payload[self.attr] = self.min_mireds
            
    def encode(self, device: "SymiDevice", payload: dict, value: Any):
        # Convert from mireds to Kelvin
        if value > 0:
            kelvin = int(1000000 / value)
            payload[self.prop] = kelvin
        else:
            payload[self.prop] = 6500  # Default


class EventConv(Converter):
    """Event converter for sensors."""
    
    def __init__(self, attr: str, **kwargs):
        super().__init__(attr, domain='sensor', **kwargs)
        
    def decode(self, device: "SymiDevice", payload: dict, value: Any):
        payload[self.attr] = str(value)


class NumericConv(Converter):
    """Numeric converter."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.min_value = kwargs.get('min_value')
        self.max_value = kwargs.get('max_value')
        self.step = kwargs.get('step', 1)
    
    def decode(self, device: "SymiDevice", payload: dict, value: Any):
        try:
            num_value = float(value)
            if self.min_value is not None:
                num_value = max(num_value, self.min_value)
            if self.max_value is not None:
                num_value = min(num_value, self.max_value)
            payload[self.attr] = num_value
        except (ValueError, TypeError):
            payload[self.attr] = 0
            
    def encode(self, device: "SymiDevice", payload: dict, value: Any):
        try:
            payload[self.prop] = float(value)
        except (ValueError, TypeError):
            payload[self.prop] = 0


class MapConv(Converter):
    """Map converter for enum values."""
    
    def __init__(self, *args, map_dict: dict = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.map_dict = map_dict or {}
        self.reverse_map = {v: k for k, v in self.map_dict.items()}
    
    def decode(self, device: "SymiDevice", payload: dict, value: Any):
        payload[self.attr] = self.map_dict.get(value, value)
        
    def encode(self, device: "SymiDevice", payload: dict, value: Any):
        payload[self.prop] = self.reverse_map.get(value, value)


# Convenience aliases
PropBoolConv = BoolConv
PropConv = NumericConv
PropMapConv = MapConv
ColorTempKelvin = ColorTempConv
ColorRgbConv = NumericConv  # Simplified for now
DurationConv = NumericConv
MotorConv = BoolConv
SceneConv = EventConv
