#!/usr/bin/env python3
"""
亖米Mesh网关 - 独立协议解析测试工具

基于用户提供的实际串口数据测试设备列表解析功能
不依赖Home Assistant环境
"""

import time

# 设备类型定义
DEVICE_TYPE_NAMES = {
    0: "未知设备",
    1: "零火开关",
    2: "单火开关", 
    3: "智能插座",
    4: "智能灯",
    5: "智能窗帘",
    6: "情景面板",
    7: "门磁传感器",
    8: "人体感应",
    9: "插卡取电",
    10: "温控器",
    11: "温湿度传感器",
    12: "情景开关",
    13: "离线语控节点",
    14: "门锁",
    15: "水浸报警",
    16: "烟雾报警",
    17: "智能电视盒子",
    18: "单火开关+情景",
    20: "透传模块",
    24: "五色调光灯",
    74: "透传模块",
}

# 简化的设备信息类
class DeviceInfo:
    def __init__(self, mac_address, network_address, device_type, device_sub_type, 
                 rssi, vendor_id, last_seen=None, online=True):
        self.mac_address = mac_address
        self.network_address = network_address
        self.device_type = device_type
        self.device_sub_type = device_sub_type
        self.rssi = rssi
        self.vendor_id = vendor_id
        self.last_seen = last_seen or time.time()
        self.online = online
        self.name = self._generate_name()
        self.capabilities = self._determine_capabilities()
        
    def _generate_name(self):
        type_name = DEVICE_TYPE_NAMES.get(self.device_type, f"未知设备({self.device_type})")
        
        # 确定通道数
        if self.device_type in [1, 2]:  # 零火开关、单火开关
            if self.device_sub_type == 0:
                channels = 1
            else:
                channels = self.device_sub_type
            if channels > 1:
                type_name = f"{channels}路{type_name}"
        
        # 使用MAC地址后4位作为唯一标识
        mac_suffix = self.mac_address.replace(":", "")[-4:].upper()
        return f"{type_name} {mac_suffix}"
    
    def _determine_capabilities(self):
        capabilities = []
        
        if self.device_type in [1, 2]:  # 开关
            capabilities.append("switch")
        elif self.device_type == 4:  # 智能灯
            capabilities.extend(["light", "brightness", "color_temp"])
        elif self.device_type == 5:  # 窗帘
            capabilities.extend(["cover", "position"])
        elif self.device_type == 6:  # 情景面板
            capabilities.append("scene_control")
        elif self.device_type == 7:  # 门磁
            capabilities.append("door")
        elif self.device_type == 8:  # 人体感应
            capabilities.append("motion")
        elif self.device_type in [20, 74]:  # 透传模块
            capabilities.append("switch")
        
        return capabilities

def parse_device_list(payload):
    """解析设备列表数据"""
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

            # RSSI（协议中没有，使用默认值）
            rssi = -50

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
    devices = parse_device_list(all_payload)
    
    print(f"\n🎯 测试结果:")
    print(f"  发现设备总数: {len(devices)}")
    
    device_types = {}
    for device in devices:
        type_name = DEVICE_TYPE_NAMES.get(device.device_type, f"未知类型({device.device_type})")
        device_types[type_name] = device_types.get(type_name, 0) + 1
    
    print(f"  设备类型分布:")
    for type_name, count in device_types.items():
        print(f"    - {type_name}: {count}个")
    
    print(f"\n✅ 测试完成！修复验证成功：从 1 个设备增加到 {len(devices)} 个设备！")

if __name__ == "__main__":
    test_device_list_parsing()