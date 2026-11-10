@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [ShyHealthHelper] 正在创建虚拟环境...
  python -m venv .venv
  if errorlevel 1 (
    echo 创建虚拟环境失败，请确认已安装 Python 3.10+ 并加入 PATH。
    pause
    exit /b 1
  )
)

.venv\Scripts\python.exe -c "import fastapi, requests, cryptography" >nul 2>&1
if errorlevel 1 (
  echo [ShyHealthHelper] 正在安装/更新依赖...
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 (
    echo 依赖安装失败，请检查网络后重试。
    pause
    exit /b 1
  )
)

if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo [ShyHealthHelper] 已生成 .env，请填入 DEEPSEEK_API_KEY 后重新运行。
  echo            未填写时会以 Mock 演示模式运行。
)

netstat -ano | findstr ":8000" | findstr "LISTENING" >nul
if not errorlevel 1 (
  echo.
  echo [ShyHealthHelper] 8000 端口已被占用，可能是之前启动的后端还在运行。
  echo            如果浏览器能打开 http://127.0.0.1:8000 ，可以直接使用。
  echo            如需重新启动，请先在任务管理器结束旧的 python.exe，或关闭旧后端窗口。
  echo.
  pause
  exit /b 1
)

echo.
echo [ShyHealthHelper] 启动服务：http://127.0.0.1:8000
echo            手机访问：http://本机局域网IP:8000
echo            按 Ctrl+C 停止。
echo.
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000

echo.
echo [ShyHealthHelper] 服务已退出或启动失败，请查看上面的错误信息。
pause
