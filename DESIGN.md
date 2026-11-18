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
  outline: "#D0DCE4"
  divider: "#E7EEF2"
  control-outline: "#6F8695"
  ocean: "#163B51"
  ocean-deep: "#102F42"
  mint: "#B8F1D9"
  primary-wash: "#E3F4ED"
  focus: "#245EAA"
  focus-wash: "#E2EDF9"
  waiting: "#7A4A0C"
  waiting-wash: "#F8EDD8"
  danger: "#9C3436"
  danger-wash: "#FBE9E9"
typography:
  body:
    fontFamily: "Segoe UI, Microsoft YaHei UI, sans-serif"
  number:
    fontFamily: "Consolas, monospace"
rounded:
  masthead: "12px"
  panel: "12px"
  surface: "8px"
  control: "7px"
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
  status-online:
    backgroundColor: "{colors.primary-wash}"
    textColor: "{colors.primary}"
  status-waiting:
    backgroundColor: "{colors.waiting-wash}"
    textColor: "{colors.waiting}"
  status-error:
    backgroundColor: "{colors.danger-wash}"
    textColor: "{colors.danger}"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
  checkbox:
    backgroundColor: "{colors.surface}"
    borderColor: "{colors.control-outline}"
  checkbox-checked:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
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

顶部深蓝条带连接 Nwake 标识与右侧在线计数，薄荷色用于计数和图标灯。白色面板承载设备、扫描和表单，用浅蓝灰分隔行列。状态色标始终带文字，绿色表示在线，琥珀色表示等待上线，红色表示检测异常。浅蓝色标出活动行，复选框表示批量操作范围。Segoe UI 和微软雅黑用于界面，Consolas 用于网络地址和计数。

## 布局与组件

主窗口默认 570×498，最小 470×404 个逻辑像素。列表工具、表格和选中行操作共用一个面板，唤醒操作和检测反馈位于底部。扫描窗口默认 620×454，最小 510×376。表格随窗口伸缩，超出高度时在表格内滚动。面板、表格和输入控件依次使用 12、8、7 px 圆角。截断的主机名可通过工具提示查看。

扫描窗口顶部显示网段、扫描进度和已识别主机名数量。查询中的行显示「查询中」，完成后缺少名称的行显示「未识别」。实时反馈与出错状态共用位置，勾选和添加操作留在底部。

实心强调色用于唤醒或保存，浅绿色突出扫描入口。移除确认使用红色操作按钮。发送中和扫描中保留按钮尺寸，键盘焦点有独立的蓝色描边。添加和编辑共用表单面板，校验失败时在固定提示区说明原因，并聚焦对应输入框。

## 运行时映射

`nwake/theme.py` 实现颜色、字体、Qt 样式和图标，`nwake/device_table.py` 负责两处设备表格的行高、键盘操作和状态色标。`nwake/dialogs.py` 统一表单与确认反馈。交互见 [UX-CONTRACT.md](UX-CONTRACT.md)。
