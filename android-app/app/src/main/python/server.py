"""启动内嵌的 ShyHealthHelper FastAPI 服务（Chaquopy 试验版）。"""

from __future__ import annotations

import asyncio
import os
import threading

_started = False


def _run(data_dir: str, web_dir: str, host: str, port: int) -> None:
    os.environ["APP_DATA_DIR"] = data_dir
    os.environ["APP_WEB_DIR"] = web_dir

    import uvicorn
    from app.main import app

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="info",
        loop="asyncio",
        access_log=False,
    )
    server = uvicorn.Server(config)
    # Android 上没有传统信号处理，且不能在非主线程注册信号处理器。
    server.install_signal_handlers = lambda: None
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(server.serve())


def start(data_dir: str, web_dir: str, host: str = "127.0.0.1", port: int = 8000) -> bool:
    global _started
    if _started:
        return True
    os.environ["APP_DATA_DIR"] = data_dir
    os.environ["APP_WEB_DIR"] = web_dir
    thread = threading.Thread(
        target=_run,
        args=(data_dir, web_dir, host, port),
        daemon=True,
    )
    thread.start()
    _started = True
    return True
