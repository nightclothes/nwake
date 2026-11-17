# Nwake · 局域网开机

Nwake 是一个常驻 Windows 通知区域的 Wake-on-LAN 工具。点击任务栏右下角的 Nwake 图标打开电脑列表，查看主机名、IPv4 和在线状态，也可以勾选一台或多台电脑发送唤醒包。关闭列表会收回托盘；右键托盘图标，选择「退出 Nwake」可结束程序。

## 开始使用

1. 在 Windows x64 上双击 `dist/Nwake.exe`，无需另外安装 Python。
2. 点击「添加电脑」，输入主机名或备注、目标 IPv4 和支持 WOL 的网卡 MAC 地址。通常可以留空「子网前缀」。
3. 勾选目标，点击「唤醒所选」。软件会继续检测状态；收到目标地址的 Ping 回复后才显示「在线」。
4. 找不到图标时，点击任务栏通知区域的 `^` 查看隐藏图标。Windows 决定图标是否显示在任务栏上，可以在任务栏设置中调整。

首次唤醒可让同一局域网内已启用 Wake-on-LAN 的电脑进入睡眠后测试。关机后能否唤醒因机型而异。[Microsoft 的 WOL 说明](https://learn.microsoft.com/zh-cn/windows/win32/power/system-power-states#wake-on-lan-behavior)

首次保存电脑时，Nwake 会在 `Nwake.exe` 的同级目录创建 `hosts.json`。替换 EXE 时保留这份文件即可保留电脑列表，换目录时一起移动两个文件。旧版配置的位置和迁移方法见[技术文档](docs/technical.md#本地数据)。

## 项目文档

- [需求文档](docs/requirements.md)：用户流程、首版范围与验收条件。
- [架构文档](docs/architecture.md)：模块职责、数据流与托盘生命周期。
- [技术文档](docs/technical.md)：Magic Packet、状态判定、配置格式和排障。
- [开发文档](docs/development.md)：虚拟环境、测试、打包与实机验收。
- [界面设计](DESIGN.md)和[交互约定](UX-CONTRACT.md)。
