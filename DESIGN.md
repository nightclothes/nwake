---
version: alpha
name: Nwake
description: "Windows 通知区域内的局域网开机工具，外观取自小型网关的状态面板。"
colors:
  primary: "#0D6559"
  background: "#EAF0F4"
  surface: "#FFFFFF"
  subtle: "#F3F7FA"
  ink: "#142E3E"
  muted: "#495F6C"
  outline: "#CDD9E0"
  ocean: "#163B51"
  mint: "#B8F1D9"
  focus: "#245EAA"
  waiting: "#7A4A0C"
  danger: "#9C3436"
typography:
  body:
    fontFamily: "Segoe UI, Microsoft YaHei UI, sans-serif"
  number:
    fontFamily: "Consolas, monospace"
rounded:
  masthead: "12px"
  surface: "8px"
  control: "6px"
spacing:
  window-padding: "16px"
  block-gap: "12px"
  host-row: "36px"
components:
  masthead:
    backgroundColor: "{colors.ocean}"
    textColor: "{colors.mint}"
    rounded: "{rounded.masthead}"
  button:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
  button-danger:
    backgroundColor: "{colors.danger}"
    textColor: "{colors.surface}"
  table:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.surface}"
  table-header:
    backgroundColor: "{colors.subtle}"
    textColor: "{colors.muted}"
  status-waiting:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.waiting}"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
  input-selection:
    backgroundColor: "{colors.focus}"
    textColor: "{colors.surface}"
  dialog:
    backgroundColor: "{colors.background}"
    textColor: "{colors.ink}"
---

# Nwake 界面设计

## 概览

把列表做成常放在桌面边缘的小型网关状态面板。用户停留几秒就能看到在线台数、找到一行数据或发出唤醒操作。外观的识别点是深蓝条带右侧的薄荷色在线计数，以及同样配色的 N 形托盘灯。简体中文为产品界面语言，品牌名、IP、MAC 保持原写法。

## 色彩与排版

深蓝 `ocean` 定位面板，`mint` 只用于在线计数和图标灯。白色承载表格和输入，几档浅蓝灰提供边界和选中状态。行状态始终有文字；绿色、琥珀色、红色分别辅助区分在线、等待和异常。界面使用一套浅色外观和可见的蓝色键盘焦点。Segoe UI 和微软雅黑用于界面，Consolas 用于 IPv4 和计数。

## 布局与组件

窗口默认 550×466，最小 470×400 个逻辑像素。中部表格随窗体伸缩，超出高度时在表格内滚动；底部实时检测、反馈和唤醒操作留在固定区域。顶部条带、表格和控件依次用 12、8、6 px 圆角，使用底色与线框区分层次，没有装饰阴影或动画。主机名截断时保留完整工具提示，可在编辑窗读取。

表格以短状态词显示检测结果。工具提示用于查看检测异常的具体原因，页脚在执行操作后显示反馈。

实心强调色只用于唤醒或保存这类主操作。删除确认使用危险色；禁用和发送中使用固定尺寸，焦点不会因刷新移动。表单错误在固定的提示区显示，输入仍留在原位。

## 运行时映射

`nwake/theme.py` 是颜色、状态文字、通用 Qt 样式和图标的运行时定义；此文档记录视觉角色与相同的基础值。`nwake/window.py` 持有窗口与表格尺寸，`nwake/dialogs.py` 持有统一的表单与确认样式。交互见 [UX-CONTRACT.md](UX-CONTRACT.md)。
