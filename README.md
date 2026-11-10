# ShyHealthHelper · 女性周期健康助手

> 这是 `D:\vscode\pycode\3` 的 **Chaquopy 内嵌 Python 试验副本**。安卓工程、APK 和兼容改动见 [`android-app/README.md`](android-app/README.md)。
>
> **1.3.1 内置版 APK**：`android-app/ShyHealthHelper-v1.3.2.apk`（versionCode 9 / versionName 1.3.2），完全在手机运行，可从 1.1 覆盖升级并保留数据；包含自适应安全区、运动页折叠、计划偏好、首页每日计划、折叠箭头和小米二次验证修复。

> 这是 `D:\vscode\pycode\2` 试验副本。安卓 WebView 壳、APK 和构建说明见 [`android-app/README.md`](android-app/README.md)。原项目 `D:\vscode\pycode\1` 未被修改。

一个可在手机浏览器使用的个人健康应用：记录月经并预测周期（支持不稳定周期的趋势拟合）、拍照记录饮食并由 DeepSeek 估算营养、按日统计热量并推荐下一餐、运动截图识别与小米运动健康直连、长期体重趋势与建议，以及记账（附微信小程序记账端）。

> 所有数据默认保存在本机 SQLite 中，服务端单用户运行，适合个人或家庭自用。

## 功能

1. **月经记录与提醒**
   - 记录开始/结束日期、经量、症状与备注
   - 根据最近周期自动预测下次月经、排卵日、易孕期
   - 周期不稳定时按最近周期做线性拟合，给出拟合预测值、预测窗口、波动与趋势
   - 日历展示实际经期、预测经期、易孕期与排卵日
   - 周期提醒：临近经期、月经推迟、易孕期、周期波动、持续记录建议
   - 可开启浏览器通知（页面打开时提醒）
2. **饮食拍照识别与营养估算**
   - 拍照后由 DeepSeek 视觉模型识别食物，可补充文字描述份量或口味
   - 文字描述与照片冲突时，以文字描述为准
   - 估算热量、蛋白质、脂肪、碳水、膳食纤维、糖、钠
   - 给出健康分、针对本餐的建议和当日小贴士
   - 保存饮食历史，可回看或删除
   - **按日汇总热量与营养**：自动累计当天所有餐次，按体重和目标估算每日推荐热量并计算剩余额度
   - **下一餐推荐**：记录早餐、午餐后，直接根据热量、蛋白质、体重、目标和今日运动推荐下一餐及当天还可做的运动
   - **每日热量缺口**：按 TDEE + 今日运动消耗 - 今日摄入计算热量缺口/盈余，并在首页和饮食页展示
3. **周期化运动建议 + 运动记录**
   - 身体档案：出生年份、身高、体重、活动水平、目标、伤病
   - 自动计算 BMI、基础代谢 BMR、每日总消耗 TDEE
   - 结合当前月经周期阶段（经期/卵泡期/排卵期/黄体期），由 DeepSeek 生成一周训练计划
   - 经期自动降低强度并给出安全提示；生成计划时会参考最近运动记录，避免突然加量
   - **截图识别运动记录**：上传运动 App / 手环截图，由 DeepSeek 识别日期、项目、时长、卡路里、距离、步数、心率
   - **截图缺热量自动估算**：截图只有时长/距离/步数时，按体重与运动类型用 MET 估算热量，并标记“热量估算”
   - **文字描述记录运动**：输入“快走30分钟，然后做了20分钟力量训练”，AI 解析多条记录并估算消耗
   - **估算热量参与每日计算**：估算结果进入当日运动消耗与“TDEE + 运动 - 摄入”的热量缺口
   - **小米运动健康直连**：输入小米账号密码登录一次，之后自动同步步数、睡眠、体重和运动记录；支持图片验证码与短信/邮箱二次验证
   - **长期体重与身体数据**：记录体重、体脂、肌肉量、腰围、睡眠、静息心率、步数，绘制趋势图并给出规则建议
   - **目标体重与期望日期**：设置目标体重和完成日期后，按 1 kg≈7700 千卡自动计算每日热量缺口/盈余和每周变化，并提示计划是否过激
4. **运动/身体趋势分析**
   - 体重按最小二乘计算每周变化与累计变化，区分下降、上升、稳定
   - 结合 BMI、健康体重范围、目标（减脂/保持/增肌）、睡眠、步数、静息心率给出建议
   - 短期波动提示，避免被单日水分波动误导
5. **记账 + 微信小程序（网页端已隐藏）**
   - 网页端记账入口已隐藏；后端 `/api/finance` 接口保留给微信小程序和外部调用
   - `wechat-miniprogram/` 是独立的微信小程序记账端，连接同一后端，数据实时同步
6. **首页今日概览与主题颜色**
   - 首页显示今日饮食热量与营养、热量缺口、运动消耗、目标计划
   - 顶部可切换玫瑰 / 海洋 / 森林 / 薰衣草 / 日落五种主题色，并记住选择
7. **AI 营养与运动对话**
   - 新增「对话」页，可直接向 DeepSeek 询问营养、饮食、运动和热量缺口问题
   - 每次对话自动带上体重、目标、今日饮食、运动消耗和热量缺口
   - 对话保存在本机 SQLite，自动带最近 20 条消息作为多轮记忆；可一键清空

## 技术栈

- 后端：Python 3.10+、FastAPI、SQLite、httpx、requests、cryptography
- 前端：原生 HTML/CSS/JavaScript 手机网页 + PWA（可添加到主屏幕）
- AI：DeepSeek `deepseek-flash`（OpenAI 兼容接口，支持文本、图片理解与 JSON Output）
- 小程序：微信原生小程序（WXML/WXSS/JS）

## 快速开始（Windows）

```bat
run.bat
```

首次运行会自动创建 `.venv`、安装依赖，并从 `.env.example` 生成 `.env`。

也可以手动执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

打开 <http://127.0.0.1:8000>，接口文档在 <http://127.0.0.1:8000/docs>。

### 配置 DeepSeek

在 [DeepSeek 开放平台](https://platform.deepseek.com/) 创建 API Key，写入 `.env`：

```ini
DEEPSEEK_API_KEY=sk-xxxxxxxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
DEEPSEEK_VISION_MODEL=deepseek-flash
```

重启服务后，页面右上角会显示 **DeepSeek 已连接**。

`deepseek-flash` 支持图片理解与 JSON Output：带照片的请求会自动使用 `DEEPSEEK_VISION_MODEL`（默认也是 `deepseek-flash`），支持 JPEG/PNG/GIF/WebP。模型细节见 [官方图像理解文档](https://api-docs.deepseek.com/zh-cn/guides/vision)。

没有 Key 或设置 `AI_MOCK=1` 时进入 **Mock 演示模式**：其余功能正常，饮食与运动建议使用内置示例数据，便于先体验流程。API Key 只保存在服务端环境变量中，不会下发到浏览器。

### 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` | 空 | DeepSeek API Key，空则 Mock 模式 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | API 地址 |
| `DEEPSEEK_MODEL` | `deepseek-flash` | 文本请求模型 |
| `DEEPSEEK_VISION_MODEL` | `deepseek-flash` | 带图片的请求使用的视觉模型（`deepseek-v4-pro` 不支持图片） |
| `DEEPSEEK_TIMEOUT` | `60` | 请求超时（秒） |
| `AI_MOCK` | 空 | 设为 `1` 强制 Mock |
| `APP_DATA_DIR` | `./data` | 数据目录 |
| `APP_DB_PATH` | `./data/app.db` | SQLite 路径 |
| `MAX_UPLOAD_MB` | `8` | 图片大小上限 |

## 手机访问

1. 电脑与手机连接同一个 Wi-Fi。
2. 在电脑执行 `ipconfig`，找到 IPv4 地址（例如 `192.168.1.10`）。
3. 手机浏览器访问 `http://192.168.1.10:8000`。
4. 首次启动时 Windows 防火墙弹窗请选择“允许访问”。

`run.bat` 已使用 `--host 0.0.0.0`，允许局域网访问。

### 添加为 PWA 应用

- Android Chrome/Edge：菜单 →「添加到主屏幕」
- iOS Safari：分享 →「添加到主屏幕」

> 注意：完整 PWA（Service Worker 离线缓存、安装能力）需要 **HTTPS 或 localhost**。局域网 HTTP 下页面功能可正常使用，但部分浏览器不允许注册 Service Worker。正式使用建议用 Caddy/Nginx 配置 HTTPS，或用内网穿透工具提供 HTTPS 地址。

## 微信小程序记账端

目录：`wechat-miniprogram/`

1. 用 [微信开发者工具](https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html) 导入该目录。
2. 项目已使用 `touristappid`（游客 AppID），可直接在开发者工具中预览；正式发布需替换为自己的小程序 AppID。
3. `project.config.json` 已设置 `"urlCheck": false`，开发阶段无需配置合法域名。
4. 后端地址在 `wechat-miniprogram/app.js`：

```js
globalData: {
  apiBase: "http://127.0.0.1:8000",
}
```

- 开发者工具模拟器：保持 `127.0.0.1:8000`。
- 真机调试：改成电脑局域网 IP，例如 `http://192.168.1.10:8000`，并确保手机与电脑同一网络、后端已启动。
- 正式发布：需要 HTTPS 域名、真实 AppID，并在小程序后台「开发管理 → 开发设置 → 服务器域名」配置 request 合法域名。

小程序功能与网页端记账完全同步：月度收支、分类占比、账单列表、新增/删除记录。

## 运动记录与手环数据

### 小米运动健康直连（推荐）

1. 打开「运动」页，在「小米运动健康直连」卡片输入小米账号（手机号/邮箱/小米 ID）、密码，选择中国大陆或海外区。
2. 点击「连接小米运动健康」。如果账号要求图片验证码或短信/邮箱二次验证，按页面提示输入即可。
3. 连接成功后会自动同步最近 7 天数据；之后可在卡片中选择 7/30/90 天并点击「立即同步」。
4. 同步内容包括：每日步数、睡眠时长、体重/体脂/肌肉量/腰围、运动记录（类型、时长、距离、卡路里、心率）。

**凭证安全**：账号密码、passToken 与 serviceToken 使用 Fernet 加密后保存在 `data/xiaomi_credentials.enc`，密钥在 `data/xiaomi.key`（权限 600）。这些数据只用于访问你自己的小米账号，不会上传到第三方。

> 直连使用小米运动健康的**非官方**登录态接口（社区逆向实现，参考 MIT 项目 [Aaron-gx/mihealth-api](https://github.com/Aaron-gx/mihealth-api)）。接口可能随 App 更新失效；失效时可重新连接，或改用下面的文件导入。

### 截图识别

1. 打开「运动」页，在「运动记录」卡片上传运动 App 或手环的截图。
2. 可补充说明（例如“这是今天的小米运动记录”）。
3. 点击「识别截图并保存」。Mock 模式只返回示例记录；配置 DeepSeek 后可识别真实截图。
4. 识别结果会出现在「运动历史」，可删除错误记录。

## 每日热量与下一餐推荐

1. 打开「饮食」页顶部的「当日热量与推荐」，可切换日期查看任意一天。
2. 页面会累计当天所有饮食记录的热量、蛋白质、脂肪、碳水。每日推荐热量按体重与目标估算：减脂约 26 kcal/kg、保持约 30 kcal/kg、增肌约 34 kcal/kg；没有体重时回退到 TDEE。
3. 点击「推荐下一餐 / 今日运动」：系统直接根据已摄入热量与营养、剩余额度、体重、目标、已记录餐次和今日运动，推荐下一餐的具体菜品、份量、热量，以及今天还可以做的运动。
4. 推荐在 Mock 模式下使用内置规则；配置 DeepSeek 后由模型基于同一组数据生成更个性化的简短建议。

## 每日热量缺口与 AI 对话

- 热量缺口 = `TDEE + 今日运动消耗 - 今日摄入`；正数为缺口，负数为盈余。
- 运动页可设置**目标体重**和**期望完成日期**；系统按 `1 kg 脂肪 ≈ 7700 千卡` 计算每日所需缺口/盈余，并反推每日推荐热量。
- 如果按期望时间计算出的每日热量低于安全下限（女性 1200 / 男性 1500 千卡），页面会提示计划过激并建议延长时间。
- 首页「今日概览」和饮食页都会显示缺口/盈余与目标计划；运动消耗按额外训练叠加，仅作参考。
- 「对话」页可问：今天晚餐吃什么、蛋白质够不够、今天还适合做什么运动。
- 对话上下文会带上体重、目标、今日营养、运动消耗、热量缺口和月经周期阶段；最近 20 条消息保存在 `chat_messages` 表。
- Mock 模式会返回基于今日数据的示例回答；配置 DeepSeek 后使用真实对话模型。

## 主要接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 服务状态、AI 模式 |
| GET/PUT | `/api/profile` | 身体档案、目标体重/期望日期、BMI/BMR/TDEE、目标计划 |
| GET | `/api/cycle/overview` | 周期状态、预测、提醒、历史 |
| GET | `/api/cycle/calendar?year=&month=` | 日历标记 |
| GET/POST | `/api/cycle/periods` | 经期列表 / 新增 |
| PUT/DELETE | `/api/cycle/periods/{id}` | 修改 / 删除 |
| POST | `/api/diet/analyze` | 饮食分析（multipart：photo、meal_type、可选 description；可只传照片） |
| GET | `/api/diet/daily?date=YYYY-MM-DD` | 按日热量/营养汇总、目标与运动上下文 |
| POST | `/api/diet/recommend` | 结合当日饮食与运动推荐下一餐和运动（JSON：`date`、可选 `meal_type`） |
| GET | `/api/diet/logs` | 饮食历史 |
| DELETE | `/api/diet/logs/{id}` | 删除饮食记录 |
| POST | `/api/exercise/plan` | 生成一周运动计划 |
| GET | `/api/exercise/plans` | 历史运动计划 |
| POST | `/api/exercise/logs/analyze` | 上传运动截图并识别保存（multipart：photo、note；缺热量自动估算） |
| POST | `/api/exercise/logs/describe` | 用文字描述运动，解析并估算热量后保存（JSON：description、log_date） |
| GET | `/api/xiaomi/status` | 小米运动健康连接状态 |
| POST | `/api/xiaomi/login` | 账号密码登录 / 验证码 / 二次验证 |
| POST | `/api/xiaomi/sync?days=7` | 从小米云端同步步数、睡眠、体重与运动记录 |
| POST | `/api/xiaomi/logout` | 断开小米账号并清除本机凭据 |
| GET | `/api/home/today?date=YYYY-MM-DD` | 首页今日饮食、运动、热量缺口与收支概览 |
| GET | `/api/chat/messages` | 对话历史（多轮记忆） |
| POST | `/api/chat` | 发送消息给 DeepSeek，返回营养/运动回答（JSON：`message`） |
| DELETE | `/api/chat/messages` | 清空全部对话 |
| GET | `/api/exercise/logs` | 运动记录列表（`limit`、`days`） |
| POST | `/api/exercise/logs` | 手动新增运动记录 |
| DELETE | `/api/exercise/logs/{id}` | 删除运动记录 |
| GET | `/api/exercise/summary?days=30` | 运动统计与建议 |
| GET/POST | `/api/body/records` | 身体数据列表 / 新增（按日期合并） |
| DELETE | `/api/body/records/{id}` | 删除身体数据 |
| GET | `/api/body/summary?days=90` | 体重趋势、均值与建议 |
| GET/POST | `/api/finance/records` | 账单列表 / 新增（支持 `external_id` 幂等） |
| DELETE | `/api/finance/records/{id}` | 删除账单 |
| GET | `/api/finance/summary?month=YYYY-MM` | 月度汇总与分类占比 |

完整字段与校验可在 `/docs` 中查看。

## 预测算法

- 过滤 15–60 天的有效周期，取最近最多 6 个周期计算平均值、中位数与波动。
- 对最近周期的开始日期做最小二乘线性拟合，用拟合斜率估计下次周期长度；周期稳定时结果与平均值一致，周期变长/变短时会跟随趋势。
- 下次月经 = 最近一次开始日期 + 拟合周期长度；同时给出 `预测窗口 = 拟合日期 ± 波动天数`。
- 周期范围跨度 ≥ 8 天或标准差 ≥ 4 天时标记为“周期波动较大”，并提示预测窗口与就医建议。
- 排卵日 ≈ 下次月经前 14 天；易孕期 = 排卵日前 5 天至后 1 天。
- 经期长度取最近记录的平均值（默认 5 天）。
- 可信度根据记录周期数量和波动计算：周期越多、波动越小，可信度越高。
- 提醒在服务端动态计算，打开页面即可看到。

预测只用于个人健康管理参考，**不能作为避孕或医疗依据**。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

51 个测试覆盖：周期预测与不稳定周期拟合、提醒、日历、Mock 饮食分析、按日热量汇总、热量缺口、目标体重/日期计划、下一餐推荐、AI 对话多轮记忆、首页今日概览、视觉请求构造、照片识别标记、图片上传与清理、HEIC 降级、运动计划与训练偏好、首页每日计划、运动截图识别与缺热量估算、文字描述运动解析、估算热量计入每日缺口、小米云端数据映射与凭据加密、小米二次验证（含 302 跳转）、身体数据趋势、记账 CRUD/月度统计/幂等更新、PWA 页面可访问。

可选 UI 自动化（需要 Edge 与 Playwright）：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
# 先启动后端，再运行：
.\.venv\Scripts\python.exe scripts\ui_check.py
```

## 项目结构

```
.
├─ app/                      FastAPI 后端
│  ├─ main.py                应用入口、静态资源挂载
│  ├─ config.py              环境配置
│  ├─ db.py                  SQLite 初始化与连接
│  ├─ schemas.py             请求校验模型
│  ├─ predictions.py         周期预测、不稳定周期拟合与日历算法
│  ├─ nutrition.py           按日热量汇总、目标与下一餐推断
│  ├─ body_trends.py         体重/身体数据趋势与规则建议
│  ├─ xiaomi/                小米运动健康直连（登录、加密、同步）
│  ├─ uploads.py             图片保存与清理
│  ├─ deepseek.py            DeepSeek 客户端、Prompt、Mock
│  ├─ health_metrics.py      BMI/BMR/TDEE
│  └─ routers/               profile/cycle/diet/exercise/body/xiaomi/home/chat/finance
├─ web/                      手机网页 / PWA
│  ├─ index.html
│  ├─ styles.css
│  ├─ app.js
│  ├─ manifest.webmanifest
│  ├─ sw.js
│  └─ icons/
├─ wechat-miniprogram/       微信小程序记账端
├─ tests/                    pytest 测试
├─ scripts/                  图标生成、UI 冒烟测试
├─ data/                     运行时数据库与上传图片（自动创建）
├─ requirements.txt
├─ .env.example
└─ run.bat
```

## 数据与隐私

- 所有业务数据存储在 `data/app.db`；上传照片在 `data/uploads/`。
- 饮食分析会把**文字描述、身体档案字段以及餐食照片（Base64）**发送给 DeepSeek 用于识别与估算；HEIC 等不支持的格式只留在本地，不发送。
- 下一餐推荐会把**今日饮食汇总、身体档案、运动记录与月经周期阶段**发送给 DeepSeek；Mock 模式下全部在本地用规则生成。
- 运动截图识别会把**截图（Base64）与补充说明**发送给 DeepSeek。
- AI 对话会把**最近 20 条对话、体重/目标、今日饮食、运动与热量缺口**发送给 DeepSeek；对话历史保存在本机 `chat_messages` 表，可随时清空。
- 小米运动健康直连会使用你保存的小米账号凭据访问**小米官方云端**，数据只拉取到本机；账号密码与 token 加密保存在本机，不会发送给 DeepSeek 或其他第三方。
- 图片按 DeepSeek 规则压缩并计费，每张最多约 1024 tokens。
- API Key 仅服务端读取，不会写入前端代码或浏览器存储。
- 未实现登录鉴权，**不要直接把服务暴露到公网**；如需公网访问，请先加 HTTPS 与身份验证，并注意个人健康数据的合规要求。

## 已知限制

- 图片识别需要配置 DeepSeek API Key；Mock 模式不会真的识别照片，只返回示例数据。
- DeepSeek 目前仅 `deepseek-flash` 支持图片输入，`deepseek-v4-pro` 仅支持文本；带照片的请求会自动使用 `DEEPSEEK_VISION_MODEL`（默认 `deepseek-flash`）。
- 支持 JPEG/PNG/GIF/WebP；部分 iPhone 的 HEIC 原图会保存留档但不参与识别，可在系统相机中改为“兼容性最佳”，或补充文字描述。
- 浏览器通知只在页面打开时触发，未实现后台推送；后台推送需要 HTTPS + Web Push/推送服务。
- 周期预测基于历史数据拟合，周期不规律、疾病、药物、压力等都会影响结果；预测窗口只代表历史波动范围。
- 小米运动健康直连使用**非官方逆向接口**，可能因小米 App 更新、账号风控、验证码或地区差异而失效；本项目不保证长期可用，失效时可重新连接。
- 直连同步的是小米云端已有数据；手环没有同步到 App/云端的数据无法获取。睡眠、体重、心率等字段依赖对应设备与授权。
- 运动截图识别受截图清晰度与模型能力影响，数值可能与原始记录有偏差，可在运动历史中删除错误记录。
- 热量缺口把 TDEE 和运动消耗直接相加，活动水平已包含训练时可能略高估；仅作趋势参考。
- AI 对话只带最近 20 条消息作为记忆，更早内容会被截断；它不能替代医生或营养师。
- 微信小程序的正式发布需要自己的 AppID、HTTPS 域名与后台域名配置；本项目提供可直接导入的开发版。

## 免责声明

营养估算、运动建议与周期预测均为参考信息，不构成医疗诊断或治疗建议。如有异常出血、严重疼痛、月经长期紊乱或运动不适，请及时咨询专业医生。
