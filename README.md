# Nwake · 局域网开机

Nwake 是一个常驻 Windows 通知区域的 Wake-on-LAN 工具。点击任务栏右下角的 Nwake 图标打开电脑列表，查看主机名、IPv4 和在线状态，也可以勾选一台或多台电脑发送唤醒包。关闭列表会收回托盘；右键托盘图标，选择「退出 Nwake」可结束程序。

## 开始使用

1. 在 Windows x64 上双击 `dist/Nwake.exe`，无需另外安装 Python。
2. 点击「扫描局域网」，勾选一台或多台设备，再点「添加所选」。也可用「添加电脑」手动填写主机名、IPv4 和网卡 MAC 地址。
3. 点击「刷新」手动检测电脑状态。勾选目标并点击「唤醒所选」后，可再次刷新确认目标是否上线。
4. 勾选要移除的电脑，点击「移除所选」。批量移除前可在确认框核对设备和数量。
5. 找不到图标时，点击任务栏通知区域的 `^` 查看隐藏图标。Windows 决定图标是否显示在任务栏上，可以在任务栏设置中调整。

首次唤醒可让同一局域网内已启用 Wake-on-LAN 的电脑进入睡眠后测试。关机后能否唤醒因机型而异。[Microsoft 的 WOL 说明](https://learn.microsoft.com/zh-cn/windows/win32/power/system-power-states#wake-on-lan-behavior)

首次保存电脑时，Nwake 会在 `Nwake.exe` 的同级目录创建 `hosts.json`。替换 EXE 时保留这份文件即可保留电脑列表，换目录时一起移动两个文件。旧版配置的位置和迁移方法见[技术文档](docs/technical.md#本地数据)。

## 项目文档

- [需求文档](docs/requirements.md)：用户流程、首版范围与验收条件。
- [架构文档](docs/architecture.md)：模块职责、数据流与托盘生命周期。
- [技术文档](docs/technical.md)：Magic Packet、状态判定、配置格式和排障。
- [开发文档](docs/development.md)：虚拟环境、测试、打包与实机验收。
- [界面设计](DESIGN.md)和[交互约定](UX-CONTRACT.md)。
