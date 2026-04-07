# 荷塘AI花生工具

这是一个基于 `PyWebView + Vue` 的桌面工具项目，主要包含：

- 花生账号管理
- 花生任务创建、轮询、导出、下载
- 微头条对标账号与文章抓取
- 文章改写、标题生成
- Windows EXE 打包与 GitHub Actions 自动构建

## 技术栈

- 前端：`Vue 3 + Vite`
- 桌面壳：`PyWebView`
- Python 依赖管理：`uv`
- 打包：`PyInstaller`
- 浏览器自动化：`Playwright`

## 本地运行

执行：

```sh
./run.sh
```

Windows 下也可以直接执行：

```bat
run.bat
```

这个脚本会完成以下操作：

- 使用 `uv` 同步 Python 依赖
- 安装前端依赖
- 构建前端页面
- 将前端产物同步到 `app/web_dist`
- 启动桌面应用

## 本地打包

执行：

```sh
./package.sh
```

Windows 下也可以直接执行：

```bat
build_exe.bat
```

这个脚本会完成以下操作：

- 使用 `uv` 同步 Python 依赖
- 重新构建前端
- 刷新 `app/web_dist`
- 安装 Playwright Chromium 到本地打包目录
- 使用 `PyInstaller` 生成桌面打包产物

默认打包输出目录：

```text
dist/荷塘AI花生工具/
```

## Windows 打包说明

当前 Windows 打包产物默认会同时弹出一个终端窗口，用来查看运行日志。

- 双击 `荷塘AI花生工具.exe` 时，会同时出现 GUI 窗口和日志终端
- 这样可以直接看到任务执行、接口请求、错误信息等日志

如果你后续不想显示终端窗口，可以在打包时设置环境变量：

```sh
HUASHENGAI_CONSOLE=0
```

## GitHub Actions 自动打包

仓库内已经包含工作流：

```text
.github/workflows/build-windows-exe.yml
```

触发方式：

- push 到 `main`
- push 到 `master`
- 手动执行 `workflow_dispatch`

工作流会自动：

- 安装 Python、Node、uv
- 构建前端
- 安装 Playwright Chromium
- 使用 `PyInstaller` 打包 Windows EXE
- 上传构建产物

上传的 artifact 名称为：

- `荷塘AI花生工具-windows-dir`
- `荷塘AI花生工具-windows-zip`

## 可选环境变量

### 自定义前端目录

```sh
WEB_DIST_DIR=/absolute/path/to/web ./run.sh
```

### 自定义打包名称

```sh
HUASHENGAI_DIST_NAME=荷塘AI花生工具 ./package.sh
```

### 自定义 Playwright 浏览器目录

```sh
PLAYWRIGHT_BROWSERS_PATH=/absolute/path/to/playwright-browsers ./package.sh
```

## 前后端通信

前端通过 `window.pywebview.api` 调用 Python：

- `ping()`
- `get_app_state()`
- `post_message(message)`
- `emit_demo_event(topic)`
- `set_window_title(title)`

Python 侧会向前端分发 `huashengai:desktop-event` 事件，前端统一监听并更新界面状态。
