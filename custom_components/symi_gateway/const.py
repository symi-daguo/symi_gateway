"""Constants for the Symi Gateway integration."""
from typing import Final

DOMAIN: Final = "symi_gateway"
DEFAULT_NAME: Final = "Symi Gateway"

# Platforms
SUPPORTED_DOMAINS = [
    "light",
    "switch",
    "binary_sensor",
]

# Default values
DEFAULT_TCP_PORT: Final = 4196

# Configuration keys
CONF_CONNECTION_TYPE: Final = "connection_type"
CONF_SERIAL_PORT: Final = "serial_port"
CONF_TCP_HOST: Final = "tcp_host"
CONF_TCP_PORT: Final = "tcp_port"
CONF_BAUDRATE: Final = "baudrate"

# Connection types
CONNECTION_TYPE_SERIAL: Final = "serial"
CONNECTION_TYPE_TCP: Final = "tcp"

# Default values
DEFAULT_BAUDRATE: Final = 115200  # 根据协议文档
DEFAULT_TCP_PORT: Final = 4196  # 默认TCP端口
DISCOVERY_PORT: Final = 4196  # 局域网发现端口
DEFAULT_TIMEOUT: Final = 3.0
DISCOVERY_TIMEOUT: Final = 5.0  # 发现超时时间

# Protocol constants
PROTOCOL_HEADER: Final = 0x53
MIN_FRAME_LENGTH: Final = 4

# Operation codes - Request (0x01-0x70)
OP_READ_BLE_NAME: Final = 0x01
OP_READ_SOFTWARE_VERSION: Final = 0x02
OP_READ_MAC_ADDRESS: Final = 0x03
OP_READ_MESH_NETKEY: Final = 0x04
OP_FACTORY_RESET: Final = 0x05
OP_REBOOT: Final = 0x06
OP_START_SCAN: Final = 0x10
OP_STOP_SCAN: Final = 0x11
OP_READ_DEVICE_LIST: Final = 0x12  # 读取设备列表
OP_ADD_DEVICE: Final = 0x12  # 添加设备 (同一个操作码，根据参数区分)
OP_DELETE_DEVICE: Final = 0x13
OP_CLEAR_ALL_DEVICES: Final = 0x14
OP_READ_DEVICE_COUNT: Final = 0x15
OP_SCENE_CONFIG: Final = 0x20
OP_SCENE_DELETE: Final = 0x21
OP_DEVICE_CONTROL: Final = 0x30
OP_SCENE_CONTROL: Final = 0x31
OP_DEVICE_STATUS_QUERY: Final = 0x32

# Operation codes - Response (0x81-0xF0)
OP_RESP_READ_BLE_NAME: Final = 0x81
OP_RESP_READ_SOFTWARE_VERSION: Final = 0x82
OP_RESP_READ_MAC_ADDRESS: Final = 0x83
OP_RESP_READ_MESH_NETKEY: Final = 0x84
OP_RESP_FACTORY_RESET: Final = 0x85
OP_RESP_REBOOT: Final = 0x86
OP_RESP_SCAN: Final = 0x90
OP_RESP_STOP_SCAN: Final = 0x91
OP_RESP_READ_DEVICE_LIST: Final = 0x92  # 读取设备列表响应
OP_RESP_DEVICE_LIST: Final = 0x92  # 设备列表响应 (别名)
OP_RESP_ADD_DEVICE: Final = 0x92  # 添加设备响应 (同一个操作码)
OP_RESP_DELETE_DEVICE: Final = 0x93
OP_RESP_CLEAR_ALL_DEVICES: Final = 0x94
OP_RESP_READ_DEVICE_COUNT: Final = 0x95
OP_RESP_SCENE_CONFIG: Final = 0xA0
OP_RESP_SCENE_DELETE: Final = 0xA1
OP_RESP_DEVICE_CONTROL: Final = 0xB0
OP_RESP_SCENE_CONTROL: Final = 0xB1
OP_RESP_DEVICE_STATUS_QUERY: Final = 0xB2

# Event codes
OP_EVENT_NODE_NOTIFICATION: Final = 0x80

# Status codes
STATUS_SUCCESS: Final = 0x00
STATUS_ERROR: Final = 0x01
STATUS_SCAN_DISCOVERY_EVENT: Final = 0x02
STATUS_PAIRING_SUCCESS_EVENT: Final = 0x03
STATUS_PAIRING_FAILED_EVENT: Final = 0x04
STATUS_NODE_ACK_EVENT: Final = 0x05
STATUS_NODE_STATUS_EVENT: Final = 0x06

# Device types (based on protocol document 3.5.2)
DEVICE_TYPE_UNKNOWN: Final = 0
DEVICE_TYPE_ZERO_FIRE_SWITCH: Final = 1  # 零火开关
DEVICE_TYPE_SINGLE_FIRE_SWITCH: Final = 2  # 单火开关
DEVICE_TYPE_SMART_SOCKET: Final = 3  # 智能插座
DEVICE_TYPE_SMART_LIGHT: Final = 4  # 智能灯
DEVICE_TYPE_SMART_CURTAIN: Final = 5  # 智能窗帘
DEVICE_TYPE_SCENE_PANEL: Final = 6  # 情景面板
DEVICE_TYPE_DOOR_SENSOR: Final = 7  # 门磁传感器
DEVICE_TYPE_MOTION_SENSOR: Final = 8  # 人体感应
DEVICE_TYPE_CARD_POWER: Final = 9  # 插卡取电
DEVICE_TYPE_THERMOSTAT: Final = 10  # 温控器
DEVICE_TYPE_TEMP_HUMIDITY: Final = 11  # 温湿度传感器
DEVICE_TYPE_SCENE_SWITCH: Final = 12  # 情景开关
DEVICE_TYPE_OFFLINE_VOICE_CONTROLLER: Final = 13  # 离线语控节点
DEVICE_TYPE_SMART_DOOR_LOCK: Final = 14  # 门锁
DEVICE_TYPE_WATER_ALARM_SENSOR: Final = 15  # 水浸报警
DEVICE_TYPE_SMOKE_ALARM_SENSOR: Final = 16  # 烟雾报警
DEVICE_TYPE_SMART_TV_BOX: Final = 17  # 智能电视盒子
DEVICE_TYPE_SINGLE_FIRE_SCENE_SWITCH: Final = 18  # 单火开关+情景
DEVICE_TYPE_TRANSPARENT_MODULE: Final = 20  # 透传模块
DEVICE_TYPE_FIVE_COLOR_LIGHT: Final = 24  # 五色调光灯
DEVICE_TYPE_TRANSPARENT_MODULE_74: Final = 74  # 透传模块(类型74)

# Device type names
DEVICE_TYPE_NAMES: Final = {
    DEVICE_TYPE_UNKNOWN: "未知设备",
    DEVICE_TYPE_ZERO_FIRE_SWITCH: "零火开关",
    DEVICE_TYPE_SINGLE_FIRE_SWITCH: "单火开关", 
    DEVICE_TYPE_SMART_SOCKET: "智能插座",
    DEVICE_TYPE_SMART_LIGHT: "智能灯",
    DEVICE_TYPE_SMART_CURTAIN: "智能窗帘",
    DEVICE_TYPE_SCENE_PANEL: "情景面板",
    DEVICE_TYPE_DOOR_SENSOR: "门磁传感器",
    DEVICE_TYPE_MOTION_SENSOR: "人体感应",
    DEVICE_TYPE_CARD_POWER: "插卡取电",
    DEVICE_TYPE_THERMOSTAT: "温控器",
    DEVICE_TYPE_TEMP_HUMIDITY: "温湿度传感器",
    DEVICE_TYPE_SCENE_SWITCH: "情景开关",
    DEVICE_TYPE_OFFLINE_VOICE_CONTROLLER: "离线语控节点",
    DEVICE_TYPE_SMART_DOOR_LOCK: "门锁",
    DEVICE_TYPE_WATER_ALARM_SENSOR: "水浸报警",
    DEVICE_TYPE_SMOKE_ALARM_SENSOR: "烟雾报警",
    DEVICE_TYPE_SMART_TV_BOX: "智能电视盒子",
    DEVICE_TYPE_SINGLE_FIRE_SCENE_SWITCH: "单火开关+情景",
    DEVICE_TYPE_TRANSPARENT_MODULE: "透传模块",
    DEVICE_TYPE_FIVE_COLOR_LIGHT: "五色调光灯",
    DEVICE_TYPE_TRANSPARENT_MODULE_74: "透传模块",
}

# Message types
MSG_TYPE_STATUS_QUERY: Final = 0x00
MSG_TYPE_SWITCH_CONTROL: Final = 0x02
MSG_TYPE_BRIGHTNESS_CONTROL: Final = 0x03
MSG_TYPE_COLOR_TEMP_CONTROL: Final = 0x04
MSG_TYPE_CURTAIN_CONTROL: Final = 0x05
MSG_TYPE_CURTAIN_POSITION: Final = 0x06
MSG_TYPE_CONTROL_SOURCE: Final = 0x0D
MSG_TYPE_SOFTWARE_VERSION: Final = 0x0F
MSG_TYPE_CONFIG_LOCK: Final = 0x11
MSG_TYPE_KEY_CONFIG_1_4: Final = 0x12
MSG_TYPE_KEY_CONFIG_5_6: Final = 0x19

# Switch control parameters
SWITCH_ALL_OFF: Final = 0x05
SWITCH_ALL_ON: Final = 0x0A
SWITCH_1_OFF: Final = 0x01
SWITCH_1_ON: Final = 0x02
SWITCH_2_OFF: Final = 0x03
SWITCH_2_ON: Final = 0x04
SWITCH_3_OFF: Final = 0x06
SWITCH_3_ON: Final = 0x07
SWITCH_4_OFF: Final = 0x08
SWITCH_4_ON: Final = 0x09
SWITCH_5_OFF: Final = 0x0B
SWITCH_5_ON: Final = 0x0C
SWITCH_6_OFF: Final = 0x0D
SWITCH_6_ON: Final = 0x0E

# Curtain control parameters
CURTAIN_OPEN: Final = 0x01
CURTAIN_CLOSE: Final = 0x02
CURTAIN_STOP: Final = 0x03


def get_gateway_device_info(entry_id: str) -> dict[str, str]:
    """Get consistent gateway device info."""
    return {
        "identifiers": {(DOMAIN, entry_id)},
        "name": "亖米Mesh网关",
        "manufacturer": "SYMI亖米",
        "model": "Mesh Gateway",
        "sw_version": "1.0",
    }
