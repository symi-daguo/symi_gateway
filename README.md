# 亖米Mesh网关 Home Assistant集成

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub release](https://img.shields.io/github/release/symi-daguo/symi_gateway.svg)](https://github.com/symi-daguo/symi_gateway/releases)
[![License](https://img.shields.io/github/license/symi-daguo/symi_gateway.svg)](LICENSE)

这是一个用于Home Assistant的亖米Mesh网关集成，支持通过串口和TCP连接网关，自动发现和控制亖米Mesh网络中的智能设备。

## 🎯 最新更新 v4.5.0

### ✨ 新功能
- **动态实体创建**: 设备发现后自动创建对应的Home Assistant实体
- **实时设备同步**: 点击"亖米读取设备列表"后立即生成所有设备实体
- **智能防重复**: 自动防止重复创建相同设备的实体
- **多通道支持**: 自动为多通道设备创建独立的控制实体

### 🔧 技术改进
- 修复了设备发现后实体不自动创建的问题
- 优化了TCP通信协议解析
- 改进了设备状态同步机制
- 增强了错误处理和日志记录

## 🌟 功能特性

### 核心功能
- **多种连接方式**: 支持串口连接 (115200波特率) 和TCP网络连接
- **设备自动发现**: 一键开启发现模式，自动扫描并添加设备
- **设备持久化**: 自动保存已发现的设备，重启后无需重新配网
- **实时状态同步**: 设备状态实时更新到Home Assistant
- **完整设备控制**: 支持开关、调光、窗帘、传感器等多种设备类型

### 支持的设备类型
- **开关类**: 零火开关(1-6路)、单火开关(1-4路)、智能插座
- **灯光类**: 智能灯(调光、色温)
- **窗帘类**: 智能窗帘(开关、位置控制)
- **传感器类**: 温湿度传感器、门磁传感器、人体感应
- **气候类**: 温控器
- **其他**: 情景面板、插卡取电

### 集成服务
- `symi_gateway.start_scan`: 开始设备扫描
- `symi_gateway.stop_scan`: 停止设备扫描
- `symi_gateway.factory_reset`: 网关恢复出厂设置
- `symi_gateway.reboot_gateway`: 重启网关

## 📋 系统要求

- Home Assistant 2023.1.0 或更高版本
- Python 3.11 或更高版本
- 串口连接或TCP网络连接到亖米网关设备
- pyserial 3.5+ (串口连接时需要)

## 🚀 安装方法

### 方法1: HACS安装 (推荐)
1. 确保已安装HACS
2. 在HACS中添加自定义存储库: `https://github.com/symi-daguo/symi_gateway`
3. 搜索并安装"Symi Gateway"
4. 重启Home Assistant
5. 在集成页面添加集成

### 方法2: 手动安装
1. 下载此集成的所有文件
2. 将 `custom_components/symi_gateway` 文件夹复制到你的Home Assistant配置目录下的 `custom_components` 文件夹中
3. 重启Home Assistant
4. 在集成页面搜索"Symi智能家居网关"并添加

## ⚙️ 配置步骤

### 1. 硬件连接
**串口连接方式：**
- 使用USB转串口线连接亖米网关到运行Home Assistant的设备
- 确保网关已上电并正常工作
- 记录串口设备路径 (如 `/dev/ttyUSB0` 或 `COM3`)

**TCP网络连接方式：**
- 确保亖米网关已连接到网络
- 确保Home Assistant设备与网关在同一网络
- 记录网关的IP地址和端口号 (通常为8899)

### 2. 添加集成
1. 进入Home Assistant的"配置" → "设备与服务"
2. 点击"添加集成"
3. 搜索"亖米Mesh网关"
4. 选择连接方式：
   - **串口连接**: 输入串口路径和波特率
   - **TCP连接**: 输入IP地址和端口号
5. 点击"提交"

### 3. 设备配网
1. 集成添加成功后，会自动创建"亖米设备发现模式"开关
2. 开启"亖米设备发现模式"开关
3. 长按要配网的设备上的配网按键3-5秒
4. 设备指示灯快速闪烁表示进入配网模式
5. 网关会自动发现设备并添加到Home Assistant
6. 设备配网成功后会自动创建对应的实体

## 🎮 使用说明

### 设备发现
- **开启发现模式**: 打开"设备发现模式"开关
- **配网设备**: 长按设备配网键直到指示灯快速闪烁
- **自动添加**: 设备会自动被发现并添加到HA
- **发现超时**: 发现模式会在120秒后自动关闭

### 设备控制
- **开关设备**: 直接在HA界面中控制开关状态
- **调光设备**: 支持亮度和色温调节
- **窗帘设备**: 支持开启、关闭、停止和位置控制
- **传感器**: 自动读取温度、湿度、照度等数据

### 服务调用
```yaml
# 开始设备扫描
service: symi_gateway.start_scan

# 停止设备扫描  
service: symi_gateway.stop_scan

# 网关恢复出厂设置
service: symi_gateway.factory_reset

# 重启网关
service: symi_gateway.reboot_gateway
```

## 🔧 故障排除

### 常见问题

#### 1. 配置界面问题
**症状**: 配置界面没有显示连接方式选择，或显示旧的字段
**解决方案**:
- 删除现有的集成配置
- 重启Home Assistant
- 清除浏览器缓存 (Ctrl+F5)
- 重新添加集成

#### 2. 没有显示设备发现开关
**症状**: 集成添加成功但没有"亖米设备发现模式"开关
**解决方案**:
- 检查日志中是否有错误信息
- 确认集成正确加载：`日志` → 搜索 "symi_gateway"`
- 重启Home Assistant
- 重新添加集成

#### 3. 串口连接失败
**症状**: 集成添加失败，提示"无法连接到串口"
**解决方案**:
- 检查串口路径是否正确
- 确认设备已连接并上电
- 检查串口权限 (Linux: `sudo usermod -a -G dialout homeassistant`)
- 确认没有其他程序占用串口

#### 4. TCP连接失败
**症状**: TCP连接配置失败
**解决方案**:
- 确认网关IP地址正确
- 检查网络连通性 (`ping 网关IP`)
- 确认端口号正确 (通常为8899)
- 检查防火墙设置

#### 5. 设备发现失败
**症状**: 开启发现模式后无法发现设备
**解决方案**:
- 确认网关已正常连接
- 检查设备是否正确进入配网模式
- 确认设备与网关距离不要太远
- 重启网关后重试

#### 6. 设备控制无响应
**症状**: 在HA中控制设备无反应
**解决方案**:
- 检查设备是否在线
- 确认网关与设备通信正常
- 重启集成或重新配网设备

### 日志调试
在 `configuration.yaml` 中添加以下配置启用详细日志:
```yaml
logger:
  default: info
  logs:
    custom_components.symi_gateway: debug
```

### 查看串口通信数据
启用调试日志后，可以在Home Assistant日志中查看详细的串口通信数据：
1. 进入 `设置` → `系统` → `日志`
2. 搜索 "symi_gateway"
3. 查看发送和接收的数据帧

### 重置集成
如果遇到问题，可以完全重置集成：
1. 删除现有集成：`设置` → `设备与服务` → 找到"亖米Mesh网关" → `删除`
2. 重启Home Assistant
3. 重新添加集成

## 📚 技术规格

- **协议版本**: 亖米Gateway Protocol V1.0
- **通信方式**: 串口 (115200 bps, 8N1) 或 TCP网络连接
- **支持设备**: 11种设备类型，50+子类型
- **网络拓扑**: Mesh网络，最大支持105个设备
- **响应时间**: < 200ms
- **数据持久化**: 自动保存设备配置

## 🤝 贡献

欢迎提交Issue和Pull Request来改进这个集成。

## 📄 许可证

本项目采用MIT许可证。

## 🔗 相关链接

- [Home Assistant官网](https://www.home-assistant.io/)
- [Symi官网](https://www.beancomm.com/)
- [问题反馈](https://github.com/symi/symi-gateway-ha/issues)

---

**注意**: 本集成需要Symi网关硬件支持，请确保您有相应的硬件设备。
