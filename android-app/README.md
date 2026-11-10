# ShyHealthHelper Chaquopy 试验版

这是 `D:\vscode\pycode\3` 里的安卓内嵌 Python 试验工程，**不修改文件夹 1 和 2**。

## 它是什么

- 使用 Chaquopy 把 Python 3.14 运行时和 FastAPI 后端打进 APK。
- App 启动时在手机内部启动 `http://127.0.0.1:8000`，WebView 加载本地页面。
- 不需要电脑后端，不需要 Tailscale/局域网；手机本身就是一个完整服务端。
- DeepSeek 和小米云仍然需要联网，但数据、SQLite、页面都在手机里。

## 已生成的 APK

```
app\build\outputs\apk\debug\app-debug.apk
ShyHealthHelper-v1.3.2.apk   # versionCode 9 / versionName 1.3.2
ShyHealthHelper-Chaquopy-v1.3.2.apk       # 同一 APK 的另一个文件名
```

当前约 27 MB，仅 **arm64-v8a**，适合大多数现代安卓手机。

## 安装与升级（保留数据）

```powershell
adb install -r ShyHealthHelper-v1.3.2.apk
```

或者把 `ShyHealthHelper-v1.3.2.apk` 发到手机，直接覆盖安装，**不要先卸载**。

- 包名仍为 `com.mooncare.app`，使用同一个 debug keystore 签名。
- versionCode 为 **7**：高于 1.1（2）、1.2（4）、1.2.1（5）和 1.2.2（6），可以覆盖升级。
- 数据目录 `files/mooncare_data/` 不变；升级时只替换 APK 代码，SQLite、上传图片、AI Key、小米凭证都会保留。
- 新版启动时会自动给 `exercise_logs` 补齐 `calories_estimated`、`duration_estimated`、`calorie_basis` 三个字段，旧记录保留并默认为“非估算”。
- 如果手机之前装过 `2` 的 WebView 壳版，壳版的数据在电脑端；手机内原内置版的数据库只要没有卸载/清除数据就还在，安装这个内置版后会重新读取它。

### 修复：升级后仍显示旧页面

1.2.1 起，App 检测到 versionCode 变化时会：

- 删除 `app_webview/`（WebView 的 Service Worker、HTTP 缓存、localStorage）
- 删除 `files/web/`，重新解压最新前端
- **不删除** `files/mooncare_data/`，数据库、上传图片、AI Key、小米凭证都保留
- 内置模式加载 `?embedded=1`，前端会跳过并注销 Service Worker

因此以后升级不需要卸载重装。若之前因为卸载导致数据丢失，只能依赖 Android 自动备份或其他备份恢复，升级本身不会删除数据。

首次启动会在内部存储创建：

- `mooncare_data/app.db`
- `mooncare_data/uploads/`
- `files/web/`（前端静态资源）

## 构建

使用文件夹 2 里的本地工具链：

```powershell
cd D:\vscode\pycode\3\android-app
.\build-apk.bat
```

或手动：

```powershell
$env:JAVA_HOME="D:\vscode\pycode\2\tools\jdk"
$env:ANDROID_HOME="D:\vscode\pycode\2\tools\android-sdk"
$env:GRADLE_USER_HOME="D:\vscode\pycode\2\tools\gradle-home"
D:\vscode\pycode\2\tools\gradle\bin\gradle.bat assembleDebug --no-daemon
```

`app/build.gradle` 里写死了构建机 Python 路径：

```gradle
buildPython("C:/Users/shy/AppData/Local/Programs/Python/Python314/python.exe")
```

换电脑时改成对应路径即可。

## 为安卓做过的兼容改动

- **Pydantic v2 → v1**：Chaquopy 没有现成的 `pydantic-core` Android wheel，因此后端改用 `pydantic==1.10.27` + `fastapi==0.99.1`。
- **uvicorn 纯 Python**：不使用 `uvicorn[standard]`，避免 `httptools/watchfiles/websockets` 原生依赖。
- **httpx 0.27.2**：兼容 FastAPI 0.99 / Starlette 0.27 的 TestClient。
- **不打包 cryptography**：小米凭据存储改用 XOR 混淆的 fallback，仅原型可用，**不是生产安全方案**。
- **静态资源**：`web/` 打进 Android assets，启动时解压到 `files/web`，通过 `APP_WEB_DIR` 告诉 FastAPI。
- **数据目录**：通过 `APP_DATA_DIR` 指向 App 内部存储。

## 已验证

- APK 编译成功。
- 桌面用同一套 Pydantic v1 依赖跑通 `51 passed`。
- 桌面调用 `server.start()` 启动内嵌 uvicorn，`/api/health`、`/api/home/today`、`/api/chat` 均正常。
- APK 内已确认包含 `assets/chaquopy`、`assets/web`、`libpython3.14.so`。

## 尚未验证/限制

- **还没在真机安装运行**：当前没有连接的安卓设备，没有做真机启动测试。
- 没有前台服务：App 切到后台后，Android 可能杀掉进程；长时间同步时建议保持 App 在前台。正式版需要加 foreground service。
- DeepSeek API Key 没有配置入口：当前是 Mock 模式；正式版需要加设置页或构建时注入。
- 小米登录从手机网络发起，可能更容易触发风控/二次验证。
- 小米凭据 fallback 只是混淆，不是加密；正式版应接入 Android Keystore 或打包 cryptography。
- 仅 arm64-v8a，不支持 x86 模拟器。
- 这是单用户 App；多用户仍需改成登录 + 数据隔离。

## 下一步

1. 把 APK 装到真机，检查启动、饮食拍照、小米登录、AI 对话。
2. 如果启动失败，看 `adb logcat | findstr python` 或 Android Studio Logcat 里的 `python.stderr`。
3. 要做正式版，再补：前台服务、DeepSeek Key 设置、Android Keystore、多用户/备份。

## 1.3.2 ????

- App ???PWA ???????? APK ????? **ShyHealthHelper**?
- ???? `com.mooncare.app`??????? `files/mooncare_data/`?????????????????
- `cxyHealthHelper` ????????????????? ShyHealthHelper ????

