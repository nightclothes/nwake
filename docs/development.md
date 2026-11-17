# 开发与发布

构建环境为 Windows x64、CPython 3.12。仓库默认分支为 `main`。如果从源码副本开始且没有 `.git`，才需要执行 `git init -b main`。

在项目根目录运行以下命令。用 `.venv` 中的 Python 不需要激活脚本，也不会改用其他项目的 Python。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m nwake
```

运行环境只依赖 PySide6 Essentials；开发安装额外包含 Ruff 和 PyInstaller。提交源码前运行：

```powershell
.\.venv\Scripts\ruff.exe format --check .
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

运行源码时，`hosts.json` 与运行期间的 `nwake.lock` 位于仓库根目录。打包后，这两个文件随 EXE 所在目录定位。

## 生成单文件 EXE

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build.ps1
```

产物为 `dist/Nwake.exe`。脚本生成图标并调用 PyInstaller 的 `--onefile --windowed`，把 Python 和 Qt 一同打包。打包时隔离构建进程的 `PATH`，防止误收集其他软件的 DLL。双击即可使用；单文件在运行期间会将运行库展开到临时目录。见 [PyInstaller 单文件文档](https://www.pyinstaller.org/en/stable/operating-mode.html)。`build/`、`dist/` 和 `.venv/` 不入 Git。

## 实机验收

1. 将 EXE 单独复制到空目录。启动后确认图标在任务栏通知区域或其隐藏图标区；关闭列表，再从托盘打开。右键退出后图标和进程应消失。
2. 在清单中添加同一广播域内至少两台真实电脑。在线时核对 IPv4 和 Ping 状态。重开应用，核对保存的记录。
3. 让已配置 WOL 的目标进入睡眠。勾选一台唤醒，确认已发送且等到在线；再将两台设备休眠，批量选中并确认唤醒。没有实体设备时，自动化测试验证报文、选择和反馈，不能代替真实电源状态验收。
