# Nwake 交互约定

产品行为来自 [需求文档](docs/requirements.md)；网络与数据细节见 [技术文档](docs/technical.md)。视觉规范见 [DESIGN.md](DESIGN.md)。

| Capability | Canonical owner | Source of truth | Verification |
| --- | --- | --- | --- |
| Table Selection | `nwake/dialogs.py` 的 `SelectAll` 与各窗口的 Qt 表格 | 主列表勾选用于唤醒，扫描结果勾选用于添加。全选作用于当前表格已显示的记录。 | `tests/test_ui.py` |
| Select/Listbox | `nwake/discovery_dialog.py` 的 Qt 下拉框 | Qt 管理菜单与键盘交互。切换网段后开始新扫描。 | `tests/test_ui.py` |
| Form | `nwake/dialogs.py` 的 `HostDialog`，调用 `nwake/hosts.py` | 添加与编辑复用表单。错误时保留输入，聚焦非法字段；成功时回到列表。 | `tests/test_ui.py`、`tests/test_core.py` |
| Scrollbar | `nwake/theme.py` | 使用全局 Qt 滚动条样式，在表格内部纵向滚动。 | 以窄窗、长列表验证。 |
| Feedback | `nwake/window.py` 的页脚与操作详情 | 区分已交给系统发送、发送失败与在线探测。后台检测不覆盖最近一次操作反馈。 | `tests/test_ui.py` |
| CRUD | `nwake/window.py` → `HostStore` | 先成功保存再变更列表；编辑、移除作用于一行。移除前确认，且只清除当前记录。 | `tests/test_ui.py`、`tests/test_core.py` |
| 扫描导入 | `nwake/discovery_dialog.py` → `nwake/window.py` → `HostStore` | 扫描结果可边查边勾选。按「添加所选」一次保存；保存失败时保留勾选。 | `tests/test_ui.py` |

托盘图标打开现有列表，关闭列表保留后台运行。托盘不可用时关闭直接退出。所有电脑列表操作都能通过 Qt 键盘焦点访问，表格当前单元格可用空格切换勾选。多台发送和移除默认焦点为取消；关闭有改动的表单前询问是否放弃。真实配置出错时显示详情并停用更改，修复后重新启动即可读取。
