# Nwake 交互约定

产品行为来自 [需求文档](docs/requirements.md)；网络与数据细节见 [技术文档](docs/technical.md)。视觉规范见 [DESIGN.md](DESIGN.md)。

| Capability | Canonical owner | Source of truth | Verification |
| --- | --- | --- | --- |
| Table Selection | `nwake/device_table.py` 的 `DeviceTable` 与 `nwake/dialogs.py` 的 `SelectAll` | 主列表勾选用于唤醒或移除，扫描结果勾选用于添加。全选作用于当前已显示的记录。勾选列整格可点，空格切换当前行勾选，Tab 移到下一控件。 | `tests/test_ui.py` |
| Select/Listbox | `nwake/discovery_dialog.py` 的 Qt 下拉框 | Qt 管理菜单与键盘交互。切换网段后开始新扫描。 | `tests/test_ui.py` |
| Form | `nwake/dialogs.py` 的 `HostDialog`，调用 `nwake/hosts.py` | 添加与编辑复用表单。错误时保留输入，聚焦非法字段；成功时回到列表。 | `tests/test_ui.py`、`tests/test_core.py` |
| Scrollbar | `nwake/theme.py` | 使用全局 Qt 滚动条样式，在表格内部纵向滚动。 | 以窄窗、长列表验证。 |
| Feedback | `nwake/window.py` 的页脚与操作详情 | 点击「刷新」才检测在线状态。操作反馈独立显示唤醒发送结果，用户可手动刷新确认上线。 | `tests/test_ui.py` |
| CRUD | `nwake/window.py` → `HostStore` | 编辑作用于当前行。移除优先作用于勾选的设备，未勾选时作用于当前行。批量移除前显示台数和设备明细，确认后一次保存。保存失败时保留列表和勾选。 | `tests/test_ui.py`、`tests/test_core.py` |
| 扫描导入 | `nwake/discovery_dialog.py` → `nwake/window.py` → `HostStore` | 可边查边勾选。勾选设备的名称查完后可添加，也可点「停止」后按 IP 添加。重扫同一网段时恢复 IP 和 MAC 均匹配的勾选。添加一次保存，保存失败时保留勾选。 | `tests/test_ui.py` |

托盘图标打开现有列表，关闭列表保留后台运行。从托盘选择「退出 Nwake」时关闭打开的对话框，有未保存的编辑时先确认是否放弃。托盘不可用时关闭列表直接退出。所有电脑列表操作都能通过 Qt 键盘焦点访问。多台发送和移除的默认焦点为取消。真实配置出错时显示详情并停用更改，修复后重新启动即可读取。
