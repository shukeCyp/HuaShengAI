# HuaShengAI Desktop Skeleton

This project uses:

- `Vue + Vite` as the frontend
- `PyWebView` as the desktop shell
- `uv` for Python environment management
- `PyInstaller` for packaging

## Scripts

`./run.sh`

- sync Python dependencies with `uv`
- install frontend dependencies
- build the Vue frontend
- copy the build output into `app/web_dist`
- launch the PyWebView window

`./package.sh`

- sync Python dependencies with `uv`
- rebuild the Vue frontend
- refresh `app/web_dist`
- install Playwright Chromium into a local bundle directory
- build a desktop bundle with `PyInstaller`

## Run

```sh
./run.sh
```

## Package

```sh
./package.sh
```

The packaged output is written to `dist/荷塘AI花生工具/`.

## GitHub Actions

The repository includes `.github/workflows/build-windows-exe.yml`.

- every push to `main` / `master` triggers a Windows build
- the workflow installs Playwright Chromium into the bundle
- the uploaded artifacts are named `荷塘AI花生工具-windows-dir` and `荷塘AI花生工具-windows-zip`

## Override the frontend target directory

```sh
WEB_DIST_DIR=/absolute/path/to/web ./run.sh
```

## Bridge overview

Frontend to Python:

- `window.pywebview.api.ping()`
- `window.pywebview.api.get_app_state()`
- `window.pywebview.api.post_message(message)`
- `window.pywebview.api.emit_demo_event(topic)`
- `window.pywebview.api.set_window_title(title)`

Python to frontend:

- the backend dispatches `window` event `huashengai:desktop-event`
- the Vue app subscribes to that event and updates UI state
- menu actions and Python API handlers both publish into the same event stream
