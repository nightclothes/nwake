# 技术说明

## 唤醒与状态

| 项目 | 实现 |
| --- | --- |
| Magic Packet | 6 个 `FF` 字节，紧接目标 MAC 的 16 次重复，总长 102 字节。每次操作向每个勾选目标发送一个 UDP 数据报，端口 9。见 [AMD Magic Packet 说明](https://docs.amd.com/r/en-US/ug1085-zynq-ultrascale-trm/Wake-up-on-Ethernet?contentId=woF07HyXSCMOBeQVhKlEzA)。 |
| 广播目标 | 默认 `255.255.255.255`。提供子网前缀后，用目标 IPv4 和前缀计算该子网的广播地址，例如 `192.168.1.20/25` 对应 `192.168.1.127`。前缀以目标实际网络为准。 |
| 状态探测 | 每约 5 秒调用一次 [Windows `IcmpSendEcho`](https://learn.microsoft.com/zh-cn/windows/win32/api/icmpapi/nf-icmpapi-icmpsendecho)，单主机超时 750 ms。同一轮未结束时不会叠加探测。只有来自目标 IPv4 且返回成功的回复才算在线。 |
| 发包反馈 | 「已发送」表示本机系统接受了数据报；UDP 没有目标端确认。对尚无在线回复的电脑显示最多约 45 秒的「等待上线」，回复成功后切换为「在线」。 |

状态包括「待检测」「在线」「无响应」「等待上线」「检测异常」。使用 DHCP 时，建议在路由器上为目标网卡保留 IPv4，避免 IP 换给另一台机器后误判状态。

## 局域网扫描

打开扫描窗口后，优先扫描 Windows 默认路由对应网卡的网段。可在下拉框切换活动网卡的 IPv4 网段。`/22` 至 `/30` 扫描整个网段，更大的网段扫描本机 IPv4 所在的 `/24`，具体范围显示在下拉框中。添加时保存实际网段前缀，以便计算唤醒广播地址。

扫描使用 Windows [SendARP](https://learn.microsoft.com/zh-cn/windows/win32/api/iphlpapi/nf-iphlpapi-sendarp) 获取同网段设备的 MAC。扫描结果也可能包含路由器等其他联网设备。程序会尝试反向解析主机名，未取得名称时用 IPv4 作为名称。可手动填写扫描未找到的电脑。

## 本地数据

配置文件 `hosts.json` 与 `Nwake.exe` 位于同一目录，采用 UTF-8 编码。首次启动可直接打开空列表，首次保存电脑时创建文件。程序目录需要写入权限。其中 `prefix` 为 `null` 时使用默认广播。

```json
{
  "version": 1,
  "hosts": [
    {
      "name": "书房电脑",
      "ip": "192.168.1.20",
      "mac": "02:12:34:56:78:9A",
      "prefix": null
    }
  ]
}
```

从旧版升级时，退出 Nwake，把 `%LOCALAPPDATA%\Nwake\hosts.json` 复制到新版 `Nwake.exe` 同级目录。如果同级目录已有电脑列表，先备份两份配置，再选择要使用的一份。`nwake.lock` 是运行期间的锁文件，迁移配置时只需复制 `hosts.json`。

如果界面显示文件不可用，先备份 `hosts.json`，再修复 JSON 或将原文件改名，最后重新打开软件。

## 连通与排障

1. 在目标 Windows 电脑上用 `hostname` 和 `ipconfig /all` 确认主机名、IPv4、子网掩码和物理地址。选择实际收包的网卡，通常是有线以太网网卡。
2. 确认目标固件和网卡支持并开启 Wake-on-LAN／Magic Packet。保持网线连接及主机供电。先从睡眠测试；Windows 快速启动关机和 S5 下无法保证唤醒，部分机型由固件独立支持。见 [Microsoft 电源状态说明](https://learn.microsoft.com/zh-cn/windows/win32/power/system-power-states#wake-on-lan-behavior)。
3. 在目标已开机时，从发送端先运行 `ping -n 1 192.168.1.20`（替换为实际 IPv4）。若未回复，检查 IP、设备连通性和目标端是否允许来自本地子网的 ICMP Echo；无须禁用防火墙。
4. 「已发送」但未唤醒时，优先核对目标网卡 MAC、固件和当前电源状态。多网卡、访客 Wi-Fi、AP 隔离或 VLAN 可能使广播到不了目标。确认两端在同一广播域；需要指定子网时填写实际前缀。
