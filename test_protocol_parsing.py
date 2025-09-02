#!/usr/bin/env python3
"""
亖米Mesh网关 - 协议解析测试工具

基于用户提供的实际串口数据测试设备列表解析功能
"""

import sys
import os

# 添加父目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from custom_components.symi_gateway.coordinator import SymiGatewayCoordinator
from custom_components.symi_gateway.device_manager import DeviceManager
from custom_components.symi_gateway.const import DEVICE_TYPE_NAMES
import time

def test_device_list_parsing():
    """测试设备列表解析功能"""
    
    # 用户提供的实际串口数据
    test_data = [
        "53 92 00 10 0B 00 1A D0 7D 3D 44 9C 1B 01 7B 00 14 00 00 00 FD",
        "53 92 00 10 0B 01 14 27 C9 20 DA CC 31 01 7B 00 01 03 01 00 5F",
        "53 92 00 10 0B 02 93 61 C8 20 DA CC 3B 01 7B 00 01 01 01 00 94",
        "53 92 00 10 0B 03 E4 53 4C 93 46 84 42 01 7B 00 04 00 00 00 4F",
        "53 92 00 10 0B 04 47 56 4C 93 46 84 43 01 7B 00 04 00 00 00 EF",
        "53 92 00 10 0B 05 3F 3E 59 46 8C AC 44 01 7B 00 01 06 01 00 D9",
        "53 92 00 10 0B 06 26 9C 1D 01 3B 1C 4A 01 7B 00 18 00 01 00 74",
        "53 92 00 10 0B 07 87 7E CF 20 DA CC 4B 01 7B 00 01 02 00 00 EF",
        "53 92 00 10 0B 08 2C D0 7D 3D 44 9C 51 01 7B 00 08 00 01 00 94",
        "53 92 00 10 0B 09 98 E0 C8 20 DA CC 52 01 7B 00 01 04 01 00 79",
        "53 92 00 10 0B 0A 97 D9 CF 20 DA CC 56 01 7B 00 01 02 01 00 49",
    ]
    
    print("🧪 亖米Mesh网关 - 设备列表解析测试")
    print("=" * 50)
    
    # 创建设备管理器
    device_manager = DeviceManager()
    
    # 创建模拟协调器
    class MockCoordinator:
        def __init__(self):
            self.device_manager = device_manager
            
        def _parse_device_list(self, payload):
            # 使用真实的解析逻辑
            from custom_components.symi_gateway.coordinator import SymiGatewayCoordinator
            from custom_components.symi_gateway.device_manager import DeviceInfo
            
            devices = []
            offset = 0

            print(f"🔍 解析设备列表数据: {payload.hex().upper()}")

            while offset < len(payload):
                if offset + 16 > len(payload):
                    print(f"⚠️ 在偏移 {offset} 处数据不完整，剩余字节: {len(payload) - offset}")
                    break

                try:
                    # 解析设备条目 (16字节)
                    device_data = payload[offset:offset+16]
                    print(f"📱 解析设备条目: {device_data.hex().upper()}")

                    # 根据 dev_list_node_rsp_t 结构解析
                    max_devices = device_data[0]   # u8 max
                    device_index = device_data[1]  # u8 index
                    
                    # 提取MAC地址 (6字节)
                    mac_bytes = device_data[2:8]   # u8 mac[6]
                    mac_address = ":".join(f"{b:02X}" for b in mac_bytes)

                    # 提取网络地址 (2字节，小端序)
                    network_address = int.from_bytes(device_data[8:10], 'little')  # u16 naddr

                    # 提取厂商ID (2字节，小端序)
                    vendor_id = int.from_bytes(device_data[10:12], 'little')  # u16 vendor_id

                    # 提取设备类型和子类型
                    device_type = device_data[12]    # u8 dev_type
                    device_sub_type = device_data[13]  # u8 dev_sub_type
                    
                    # 提取在线状态和标志
                    status_byte = device_data[14]  # 包含 online:1, only_tmall:1, status:6
                    online = bool(status_byte & 0x01)  # bit 0
                    only_tmall = bool(status_byte & 0x02)  # bit 1
                    
                    # 保留字节
                    reserved = device_data[15]  # u8 resv

                    # 计算RSSI (协议中没有，使用默认值)
                    rssi = -50  # 默认RSSI值

                    # 创建设备信息
                    device = DeviceInfo(
                        mac_address=mac_address,
                        network_address=network_address,
                        device_type=device_type,
                        device_sub_type=device_sub_type,
                        rssi=rssi,
                        vendor_id=vendor_id,
                        last_seen=time.time(),
                        online=online,
                    )

                    devices.append(device)
                    print(f"✅ 解析成功: {device.name}, MAC={mac_address}, type={device_type}, addr=0x{network_address:04X}, online={online}")

                    # 详细设备信息
                    print(f"📊 设备详情:")
                    print(f"  - 索引: {device_index}/{max_devices - 1}")
                    print(f"  - MAC: {mac_address}")
                    print(f"  - 网络地址: 0x{network_address:04X}")
                    print(f"  - 厂商ID: 0x{vendor_id:04X}")
                    print(f"  - 设备类型: {device_type} ({DEVICE_TYPE_NAMES.get(device_type, f'未知设备({device_type})')})")
                    print(f"  - 子类型: {device_sub_type}")
                    print(f"  - 在线: {online}")
                    print(f"  - 仅天猫: {only_tmall}")
                    print(f"  - 保留: 0x{reserved:02X}")
                    print(f"  - 支持能力: {', '.join(device.capabilities)}")
                    print("-" * 40)

                    offset += 16

                except Exception as err:
                    print(f"❌ 解析设备失败，偏移 {offset}: {err}")
                    if 'device_data' in locals():
                        print(f"  设备数据: {device_data.hex().upper()}")
                    break

            print(f"📋 总计解析设备: {len(devices)}")
            return devices
    
    # 模拟解析
    coordinator = MockCoordinator()
    total_devices = 0
    
    # 合并所有设备数据
    all_payload = b""
    
    for i, hex_data in enumerate(test_data):
        print(f"\n📦 处理第 {i+1} 条数据:")
        # 转换十六进制字符串为字节
        hex_string = hex_data.replace(" ", "")
        data_bytes = bytes.fromhex(hex_string)
        
        # 跳过协议头部，提取payload
        # 协议格式: Head(1) + Opcode(1) + Status(1) + Length(1) + Payload(Length) + Check(1)
        if len(data_bytes) >= 5:
            payload_length = data_bytes[3]  # Length字段
            if len(data_bytes) >= 4 + payload_length:
                payload = data_bytes[4:4+payload_length]  # 提取payload
                all_payload += payload
                print(f"  Payload: {payload.hex().upper()}")
    
    print(f"\n🔄 解析合并后的设备列表数据 ({len(all_payload)} 字节):")
    devices = coordinator._parse_device_list(all_payload)
    
    print(f"\n🎯 测试结果:")
    print(f"  发现设备总数: {len(devices)}")
    
    device_types = {}
    for device in devices:
        type_name = DEVICE_TYPE_NAMES.get(device.device_type, f"未知类型({device.device_type})")
        device_types[type_name] = device_types.get(type_name, 0) + 1
    
    print(f"  设备类型分布:")
    for type_name, count in device_types.items():
        print(f"    - {type_name}: {count}个")
    
    print(f"\n✅ 测试完成！")

if __name__ == "__main__":
    test_device_list_parsing()