/* ShyHealthHelper PWA 前端逻辑 */
(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  const MEAL_LABELS = { breakfast: "早餐", lunch: "午餐", dinner: "晚餐", snack: "加餐" };
  const MEAL_SHORT = { breakfast: "早", lunch: "午", dinner: "晚", snack: "加" };
  const FLOW_LABELS = { light: "量少", medium: "量中", heavy: "量多" };
  const GOAL_LABELS = { lose: "减脂", maintain: "保持", gain: "增肌" };
  const ACTIVITY_LABELS = {
    sedentary: "久坐少动",
    light: "轻度活动",
    moderate: "中度活动",
    active: "高度活动",
    very_active: "运动员级",
  };
  const INTENSITY_LABELS = { low: "低强度", moderate: "中强度", high: "高强度" };
  const EXPENSE_CATEGORIES = ["餐饮", "交通", "购物", "居住", "医疗", "娱乐", "学习", "人情", "其他"];
  const INCOME_CATEGORIES = ["工资", "奖金", "理财", "兼职", "红包", "其他"];
  const WEEKDAYS = ["日", "一", "二", "三", "四", "五", "六"];
  const THEMES = {
    rose: { label: "玫瑰", color: "#d96b84" },
    ocean: { label: "海洋", color: "#4f8fd8" },
    mint: { label: "薄荷", color: "#3f9d87" },
    lavender: { label: "薰衣草", color: "#7c6bd6" },
    amber: { label: "琥珀", color: "#d18b3f" },
  };
  const THEME_ALIASES = { forest: "mint", sunset: "amber" };

  const state = {
    health: null,
    profile: null,
    metrics: null,
    overview: null,
    calendarYear: new Date().getFullYear(),
    calendarMonth: new Date().getMonth() + 1,
    calendarData: null,
    flow: "medium",
    mealType: "lunch",
    financeType: "expense",
    financeMonth: "",
    periodEditingId: null,
    currentTab: "home",
    dietHistory: [],
    dietDate: "",
    dietDaily: null,
    exercisePlan: null,
    exerciseLogs: [],
    exerciseSummary: null,
    bodyRecords: [],
    bodySummary: null,
    homeToday: null,
    chatMessages: [],
    xiaomiStatus: null,
    xiaomiAttemptId: null,
    xiaomiChallengeKind: null,
  };

  let toastTimer = null;

  /* ---------------- 工具 ---------------- */

  const pad = (value) => String(value).padStart(2, "0");

  function todayISO() {
    const now = new Date();
    return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  }

  function currentMonth() {
    const now = new Date();
    return `${now.getFullYear()}-${pad(now.getMonth() + 1)}`;
  }

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => {
      switch (char) {
        case "&":
          return "&amp;";
        case "<":
          return "&lt;";
        case ">":
          return "&gt;";
        case '"':
          return "&quot;";
        default:
          return "&#39;";
      }
    });
  }

  function fmtCN(iso) {
    if (!iso) return "—";
    const [, month, day] = iso.split("-").map(Number);
    return `${month}月${day}日`;
  }

  function fmtRange(start, end) {
    if (!start || !end) return "—";
    const [sy, sm, sd] = start.split("-").map(Number);
    const [ey, em, ed] = end.split("-").map(Number);
    if (sy === ey && sm === em) return `${sm}月${sd}日 - ${ed}日`;
    return `${fmtCN(start)} - ${fmtCN(end)}`;
  }

  function fmtDateWithWeek(iso) {
    const date = new Date(`${iso}T00:00:00`);
    return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日 · 周${WEEKDAYS[date.getDay()]}`;
  }

  function money(value) {
    const number = Number(value) || 0;
    const sign = number < 0 ? "-" : "";
    return `${sign}¥${Math.abs(number).toLocaleString("zh-CN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`;
  }

  function parseNum(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number : 0;
  }

  function clampPercent(value) {
    return Math.max(0, Math.min(100, value));
  }

  function toast(message) {
    const element = $("#toast");
    element.textContent = message;
    element.classList.add("is-show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => element.classList.remove("is-show"), 2800);
  }

  function showLoading(text) {
    $("#loadingText").textContent = text || "AI 正在分析…";
    $("#loadingOverlay").classList.remove("hidden");
  }

  function hideLoading() {
    $("#loadingOverlay").classList.add("hidden");
  }

  async function request(path, options = {}) {
    const config = { method: options.method || "GET", headers: {} };
    if (options.json !== undefined) {
      config.headers["Content-Type"] = "application/json";
      config.body = JSON.stringify(options.json);
    } else if (options.form) {
      config.body = options.form;
    }

    let response;
    try {
      response = await fetch(path, config);
    } catch (error) {
      throw new Error("网络连接失败，请检查后端是否已启动");
    }

    if (!response.ok) {
      let message = `请求失败 (${response.status})`;
      try {
        const data = await response.json();
        if (typeof data.detail === "string") {
          message = data.detail;
        } else if (Array.isArray(data.detail)) {
          message = data.detail.map((item) => item.msg || "参数错误").join("；");
        }
      } catch (error) {
        /* 忽略解析失败 */
      }
      throw new Error(message);
    }
    if (response.status === 204) return null;
    return response.json();
  }

  function setSegmented(selector, value) {
    $$(`${selector} button`).forEach((button) => {
      button.classList.toggle("is-selected", button.dataset.value === value);
    });
  }

  function bindSegmented(selector, onChange) {
    const root = $(selector);
    if (!root) return;
    root.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-value]");
      if (!button) return;
      setSegmented(selector, button.dataset.value);
      onChange(button.dataset.value);
    });
  }

  /* ---------------- 初始化 ---------------- */

  async function init() {
    if (new URLSearchParams(location.search).has("embedded")) {
      const rootStyle = document.documentElement.style;
      rootStyle.setProperty("--safe-top", "0px");
      rootStyle.setProperty("--safe-bottom", "0px");
      rootStyle.setProperty("--safe-left", "0px");
      rootStyle.setProperty("--safe-right", "0px");
    }
    bindTabs();
    bindSegmented("#flowSegmented", (value) => {
      state.flow = value;
    });
    bindSegmented("#mealSegmented", (value) => {
      state.mealType = value;
    });
    bindSegmented("#financeTypeSegmented", (value) => {
      state.financeType = value;
      renderFinanceCategories();
    });

    state.financeMonth = currentMonth();
    $("#financeMonth").value = state.financeMonth;
    $("#financeDate").value = todayISO();
    $("#periodStart").value = todayISO();
    $("#bodyDate").value = todayISO();
    $("#dietDailyDate").value = todayISO();
    $("#exerciseDescribeDate").value = todayISO();
    state.dietDate = todayISO();
    renderFinanceCategories();

    bindPeriod();
    bindDiet();
    bindExercise();
    bindXiaomi();
    bindChat();
    bindAISettings();
    bindFinance();
    bindNotify();
    bindGlobalActions();
    bindTheme();
    applySavedTheme();
    registerServiceWorker();

    try {
      state.health = await request("/api/health");
    } catch (error) {
      toast(error.message);
    }
    renderMode();

    await loadProfile(true);
    await loadOverview();
    await loadHomeToday();

    const hash = (location.hash || "").replace("#", "");
    if (["home", "period", "diet", "exercise", "chat", "settings"].includes(hash)) {
      switchTab(hash, true);
    }
  }

  function renderMode() {
    const badge = $("#modeBadge");
    const hint = $("#dietModeHint");
    if (!badge) return;
    if (!state.health) {
      badge.classList.add("hidden");
      if (hint) hint.textContent = "";
      return;
    }
    if (state.health.ai_mode === "deepseek") {
      badge.classList.remove("hidden");
      badge.dataset.mode = "deepseek";
      badge.querySelector("span").textContent = "AI 已连接";
      if (hint) hint.textContent = `模型 ${state.health.model}`;
    } else {
      badge.classList.add("hidden");
      if (hint) hint.textContent = "";
    }
  }

  /* ---------------- 导航 ---------------- */

  function bindTabs() {
    $$(".tab").forEach((tab) => {
      tab.addEventListener("click", () => switchTab(tab.dataset.tab));
    });
  }

  const tabLoaders = {
    home: async () => {
      await loadProfile(false);
      await loadOverview();
      await loadHomeToday();
    },
    period: async () => {
      await loadOverview();
      if (!state.calendarData) {
        await loadCalendar(state.calendarYear, state.calendarMonth);
      }
    },
    diet: async () => {
      await Promise.all([loadDietHistory(), loadDietDaily()]);
    },
    exercise: async () => {
      await loadProfile(true);
      await Promise.all([
        loadLatestPlan(),
        loadExerciseLogs(),
        loadExerciseSummary(),
        loadBodyData(),
        loadXiaomiStatus(),
      ]);
    },
    chat: async () => {
      await loadChatHistory();
    },
    settings: async () => {
      await loadAISettings();
    },
  };

  function switchTab(name, silent = false) {
    if (!tabLoaders[name]) return;
    state.currentTab = name;
    $$(".tab").forEach((tab) => {
      tab.classList.toggle("is-active", tab.dataset.tab === name);
    });
    $$(".page").forEach((page) => {
      page.classList.toggle("is-active", page.id === `page-${name}`);
    });
    if (!silent) {
      history.replaceState(null, "", `#${name}`);
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
    tabLoaders[name]().catch((error) => toast(error.message));
  }

  function bindGlobalActions() {
    document.addEventListener("click", (event) => {
      const target = event.target.closest("[data-goto]");
      if (target) {
        switchTab(target.dataset.goto);
      }
    });
  }

  /* ---------------- 主题颜色 ---------------- */

  function applyTheme(name, persist = true) {
    const resolved = THEME_ALIASES[name] || name;
    const key = THEMES[resolved] ? resolved : "rose";
    if (key === "rose") {
      document.documentElement.removeAttribute("data-theme");
    } else {
      document.documentElement.dataset.theme = key;
    }
    const select = $("#themeSelect");
    if (select) select.value = key;
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", THEMES[key].color);
    if (persist) {
      try {
        localStorage.setItem("mooncare-theme", key);
      } catch (error) {
        /* 隐私模式下忽略 */
      }
    }
  }

  function applySavedTheme() {
    let saved = "rose";
    try {
      saved = localStorage.getItem("mooncare-theme") || "rose";
    } catch (error) {
      saved = "rose";
    }
    applyTheme(saved, false);
  }

  function bindTheme() {
    const select = $("#themeSelect");
    if (!select) return;
    select.addEventListener("change", () => {
      applyTheme(select.value);
      toast(`已切换到${THEMES[select.value]?.label || ""}主题`);
    });
  }

  /* ---------------- 首页 ---------------- */

  async function loadProfile(fillForm = false) {
    try {
      const data = await request("/api/profile");
      state.profile = data.profile;
      state.metrics = data.metrics;
      renderProfileSnapshot();
      renderMetricsChips();
      renderGoalPlan();
      if (fillForm) fillProfileForm();
    } catch (error) {
      toast(error.message);
    }
  }

  async function loadOverview() {
    try {
      state.overview = await request("/api/cycle/overview");
      renderHome();
      renderPeriodHistory();
      renderPredictionDetail();
      renderExercisePhase();
      maybeDailyNotify();
    } catch (error) {
      toast(error.message);
    }
  }

  function renderHome() {
    const overview = state.overview;
    const dateISO = overview?.today || todayISO();
    $("#homeDate").textContent = fmtDateWithWeek(dateISO);
    const hour = new Date().getHours();
    const greeting = hour < 5 ? "夜深了" : hour < 11 ? "早安" : hour < 13 ? "中午好" : hour < 18 ? "下午好" : "晚上好";
    $("#homeGreeting").textContent = `${greeting}，今天也要照顾好自己`;

    const hero = $("#heroCard");
    const reminders = $("#reminders");
    const stats = $("#homeStats");
    if (!hero) return;

    if (!overview || !overview.has_data) {
      hero.className = "card period-summary-card";
      hero.innerHTML = `
        <div class="period-summary-head">
          <span class="tag">待记录</span>
          <span class="muted small">从第一次记录开始</span>
        </div>
        <div class="period-countdown">还没有月经记录</div>
        <p class="period-summary-sub">记录一次月经后，这里会显示下次预估还有多少天。</p>
        <button type="button" class="link-btn" data-goto="period">去记录月经</button>`;
      reminders.innerHTML = "";
      stats.innerHTML = "";
    } else {
      const current = overview.current;
      const prediction = overview.prediction;
      const countdown = current.is_period_late
        ? `预计已推迟 ${current.late_days} 天`
        : current.days_until_next_period === 0
          ? "预计今天来潮"
          : `下次月经预估还有 ${current.days_until_next_period} 天`;

      hero.className = "card period-summary-card";
      hero.innerHTML = `
        <div class="period-summary-head">
          <span class="tag">${esc(current.phase_label)}</span>
          <span class="muted small">周期第 ${current.cycle_day} 天</span>
        </div>
        <div class="period-countdown">${esc(countdown)}</div>
        <p class="period-summary-sub">预计 ${fmtCN(prediction.next_period_start)} · 易孕期 ${fmtRange(prediction.fertile_window_start, prediction.fertile_window_end)}</p>
        <button type="button" class="link-btn" data-goto="period">查看月经记录</button>`;

      renderReminders(
        (overview.reminders || []).filter(
          (item) => item.type !== "period" && item.type !== "late"
        )
      );
      renderStats(overview);
    }
    renderProfileSnapshot();
  }

  function renderReminders(items) {
    const root = $("#reminders");
    if (!root) return;
    if (!items.length) {
      root.innerHTML = "";
      return;
    }
    root.innerHTML = items
      .slice(0, 3)
      .map(
        (item) => `
        <div class="reminder ${item.level === "warn" ? "reminder--warn" : ""}">
          <h4>${esc(item.title)}</h4>
          <p>${esc(item.message)}</p>
        </div>`
      )
      .join("");
  }

  function renderStats(overview) {
    const root = $("#homeStats");
    if (!root) return;
    const current = overview.current;
    const prediction = overview.prediction;
    const countdown = current.is_period_late
      ? `已推迟 ${current.late_days} 天`
      : current.days_until_next_period != null
        ? `还有 ${current.days_until_next_period} 天`
        : "记录后自动预测";

    root.innerHTML = `
      <div class="stat-card">
        <span class="stat-label">下次月经</span>
        <div>
          <div class="stat-value">${prediction.next_period_start ? fmtCN(prediction.next_period_start) : "待预测"}</div>
          <div class="stat-sub">${esc(countdown)}</div>
        </div>
      </div>
      <div class="stat-card">
        <span class="stat-label">易孕期</span>
        <div>
          <div class="stat-value">${fmtRange(prediction.fertile_window_start, prediction.fertile_window_end)}</div>
          <div class="stat-sub">排卵日 ${fmtCN(prediction.ovulation_date)}</div>
        </div>
      </div>
      <div class="stat-card">
        <span class="stat-label">平均周期</span>
        <div>
          <div class="stat-value">${prediction.average_cycle_length}<small>天</small></div>
          <div class="stat-sub">经期约 ${prediction.average_period_length} 天</div>
        </div>
      </div>
      <div class="stat-card">
        <span class="stat-label">预测可信度</span>
        <div>
          <div class="stat-value">${esc(prediction.confidence_label)}</div>
          <div class="stat-sub">基于 ${prediction.cycles_used} 个周期 · 波动 ±${prediction.cycle_variability} 天</div>
        </div>
      </div>`;
  }

  function renderProfileSnapshot() {
    const root = $("#profileSnapshot");
    if (!root) return;
    const profile = state.profile;
    const metrics = state.metrics || {};
    if (!profile) {
      root.innerHTML = `<div><h3>身体档案</h3><p>正在读取…</p></div>`;
      return;
    }
    const chips = [];
    if (profile.height_cm) chips.push(`<span class="chip">身高 ${profile.height_cm} cm</span>`);
    if (profile.weight_kg) chips.push(`<span class="chip chip--mint">体重 ${profile.weight_kg} kg</span>`);
    if (metrics.bmi) chips.push(`<span class="chip chip--gold">BMI ${metrics.bmi}</span>`);
    if (metrics.age) chips.push(`<span class="chip">${metrics.age} 岁</span>`);
    if (!chips.length) chips.push(`<span class="chip">待完善档案</span>`);

    root.innerHTML = `
      <div>
        <h3>身体档案</h3>
        <p>${esc(profile.nickname || "我的身体档案")} · ${esc(GOAL_LABELS[profile.goal] || "保持")}</p>
        <div class="snapshot-chips">${chips.join("")}</div>
      </div>
      <button type="button" class="btn btn-ghost btn-small" data-goto="exercise">${chips.length > 1 ? "编辑" : "去完善"}</button>`;
  }

  async function loadHomeToday() {
    try {
      state.homeToday = await request("/api/home/today");
      renderHomeToday();
    } catch (error) {
      /* 首页概览失败不阻塞其他内容 */
    }
  }

  function renderHomeToday() {
    const root = $("#homeToday");
    if (!root) return;
    const data = state.homeToday;
    if (!data) {
      root.innerHTML = '<div class="empty-state">暂无今日数据</div>';
      renderHomeExercisePlan(null);
      return;
    }
    $("#homeTodayDate").textContent = fmtCN(data.date);
    const diet = data.diet || {};
    const exercise = data.exercise || {};
    const exerciseEstimated = Math.round(parseNum(exercise.estimated_calories));
    const plan = (state.metrics || {}).goal_plan || {};
    const consumed = Math.round(parseNum(diet.calories));
    const target = Math.round(parseNum(diet.target_calories));
    const remaining = Math.round(parseNum(diet.remaining_calories));
    const over = remaining < 0;
    const progress = clampPercent(target ? (consumed / target) * 100 : 0);
    const balance = diet.energy_balance || {};
    const deficit = Math.round(parseNum(balance.deficit));
    const deficitText =
      deficit > 0
        ? `热量缺口 ${deficit} 千卡`
        : deficit < 0
          ? `热量盈余 ${-deficit} 千卡`
          : "热量基本平衡";
    const planDelta = Math.abs(Math.round(parseNum(plan.daily_energy_delta)));
    const planReady = plan.has_target && (plan.days_left || 0) > 0;
    const planSub = planReady
      ? `剩余 ${plan.days_left} 天 · 每日${plan.mode === "gain" ? "盈余" : "缺口"} ${planDelta} 千卡`
      : "设置目标体重和期望日期后自动计算";
    const macros = [
      `蛋白 ${Math.round(parseNum(diet.protein))}g`,
      `脂肪 ${Math.round(parseNum(diet.fat))}g`,
      `碳水 ${Math.round(parseNum(diet.carbs))}g`,
      `纤维 ${Math.round(parseNum(diet.fiber))}g`,
    ]
      .map((text) => `<span class="chip">${esc(text)}</span>`)
      .join("");

    root.innerHTML = `
      <div class="stat-card home-diet-card">
        <div class="home-today-head">
          <span class="stat-label">今日饮食</span>
          <button type="button" class="link-btn" data-goto="diet">记录饮食</button>
        </div>
        <div class="stat-value">${consumed}<small>千卡</small></div>
        <div class="stat-sub">目标 ${target || "—"} 千卡 · ${over ? `超出 ${-remaining}` : `剩余 ${remaining}`} 千卡 · ${esc(diet.status_label || "")}</div>
        <div class="calorie-track ${over ? "is-over" : ""}"><span style="width:${progress}%"></span></div>
        <div class="chips">
          <span class="chip ${balance.status === "surplus" ? "chip--gold" : "chip--mint"}">${esc(deficitText)}</span>
          ${macros}
        </div>
      </div>
      <div class="grid-2">
        <div class="stat-card">
          <span class="stat-label">今日运动</span>
          <div>
            <div class="stat-value">${Math.round(parseNum(exercise.duration_min))}<small>分钟</small></div>
            <div class="stat-sub">消耗 ${Math.round(parseNum(exercise.calories))} 千卡${exerciseEstimated ? `（估算 ${exerciseEstimated}）` : ""} · ${exercise.sessions || 0} 次</div>
          </div>
          <button type="button" class="link-btn" data-goto="exercise">去运动</button>
        </div>
        <div class="stat-card">
          <span class="stat-label">目标计划</span>
          <div>
            <div class="stat-value">${planReady ? `${parseNum(plan.target_weight_kg).toFixed(1)}<small>kg</small>` : "未设置"}</div>
            <div class="stat-sub">${esc(planSub)}</div>
          </div>
          <button type="button" class="link-btn" data-goto="exercise">去设置目标</button>
        </div>
      </div>`;

    renderHomeExercisePlan(data.exercise_plan);
  }

  function renderHomeExercisePlan(plan) {
    const root = $("#homeExercisePlan");
    if (!root) return;
    if (!plan) {
      root.classList.remove("hidden");
      root.innerHTML = `
        <div class="card-head">
          <h3>今日运动计划</h3>
          <button type="button" class="link-btn" data-goto="exercise">去生成</button>
        </div>
        <p class="muted">还没有生成运动计划，去运动页填写偏好和场地条件。</p>`;
      return;
    }

    const today = plan.today || null;
    const intensity = today?.intensity || "moderate";
    const intensityLabel = INTENSITY_LABELS[intensity] || "中强度";
    const tagClass =
      intensity === "low" ? "tag--mint" : intensity === "high" ? "" : "tag--gold";
    const preferences = plan.preferences
      ? `<span class="chip">条件：${esc(plan.preferences)}</span>`
      : "";
    root.classList.remove("hidden");
    root.innerHTML = `
      <div class="card-head">
        <h3>今日运动计划</h3>
        <button type="button" class="link-btn" data-goto="exercise">调整计划</button>
      </div>
      ${
        today
          ? `<div class="plan-day">
               <div class="day-badge">${esc(today.day || plan.weekday || "")}</div>
               <div class="plan-main">
                 <div class="plan-title">
                   ${esc(today.focus || "训练")}
                   <span class="tag ${tagClass}">${intensityLabel}</span>
                   <small>${today.duration_min || 30} 分钟</small>
                 </div>
                 <p>${esc(today.workout || "")}</p>
                 ${today.notes ? `<p>${esc(today.notes)}</p>` : ""}
               </div>
             </div>`
          : `<p class="muted">今天安排休息，注意恢复。</p>`
      }
      ${plan.summary ? `<p class="muted small">${esc(plan.summary)}</p>` : ""}
      <div class="chips">${preferences}</div>`;
  }

  /* ---------------- 浏览器通知 ---------------- */

  function bindNotify() {
    const button = $("#notifyBtn");
    if (!button) return;
    if (!("Notification" in window)) {
      button.textContent = "浏览器不支持";
      button.disabled = true;
      return;
    }
    updateNotifyButton();
    button.addEventListener("click", async () => {
      try {
        const permission = await Notification.requestPermission();
        updateNotifyButton();
        if (permission === "granted") {
          toast("已开启周期提醒");
          maybeDailyNotify(true);
        } else {
          toast("未获得通知权限，可在浏览器设置中开启");
        }
      } catch (error) {
        toast("当前环境不支持通知");
      }
    });
  }

  function updateNotifyButton() {
    const button = $("#notifyBtn");
    if (!button || !("Notification" in window)) return;
    if (Notification.permission === "granted") {
      button.textContent = "已开启";
    } else if (Notification.permission === "denied") {
      button.textContent = "已被禁用";
    } else {
      button.textContent = "开启提醒";
    }
  }

  function maybeDailyNotify(force = false) {
    if (!("Notification" in window) || Notification.permission !== "granted") return;
    const reminders = state.overview?.reminders || [];
    if (!reminders.length) return;
    const key = `mooncare-notified-${todayISO()}`;
    if (!force && localStorage.getItem(key)) return;
    const first = reminders[0];
    try {
      new Notification(`ShyHealthHelper · ${first.title}`, {
        body: first.message,
        icon: "/icons/icon-192.png",
        tag: "mooncare-daily",
      });
      localStorage.setItem(key, "1");
    } catch (error) {
      /* 某些浏览器需要 Service Worker 通知，忽略失败 */
    }
  }

  /* ---------------- 月经 ---------------- */

  function bindPeriod() {
    $("#calPrev").addEventListener("click", () => changeMonth(-1));
    $("#calNext").addEventListener("click", () => changeMonth(1));
    $("#periodForm").addEventListener("submit", submitPeriod);
    $("#periodCancel").addEventListener("click", closePeriodRecordPanel);
    $("#openPeriodRecord").addEventListener("click", openPeriodRecordPanel);
    $("#periodStart").addEventListener("change", () => {
      const start = $("#periodStart").value;
      const end = $("#periodEnd").value;
      if (end && start && end < start) $("#periodEnd").value = "";
    });

    $("#periodHistory").addEventListener("click", (event) => {
      const action = event.target.closest("[data-action]");
      if (!action) return;
      const item = action.closest(".list-item");
      const id = Number(item.dataset.id);
      if (action.dataset.action === "edit") startEditPeriod(id);
      if (action.dataset.action === "delete") deletePeriod(id);
    });
  }

  function changeMonth(delta) {
    let year = state.calendarYear;
    let month = state.calendarMonth + delta;
    if (month < 1) {
      month = 12;
      year -= 1;
    } else if (month > 12) {
      month = 1;
      year += 1;
    }
    loadCalendar(year, month);
  }

  async function loadCalendar(year, month) {
    try {
      const data = await request(`/api/cycle/calendar?year=${year}&month=${month}`);
      state.calendarYear = year;
      state.calendarMonth = month;
      state.calendarData = data;
      renderCalendar(data);
    } catch (error) {
      toast(error.message);
    }
  }

  function renderCalendar(data) {
    $("#calLabel").textContent = `${data.year}年${data.month}月`;
    const cells = [];
    for (let index = 0; index < data.first_weekday; index += 1) {
      cells.push('<span class="cal-day is-empty"></span>');
    }
    for (const day of data.days) {
      const classes = ["cal-day"];
      if (day.actual) classes.push("actual");
      else if (day.predicted) classes.push("predicted");
      if (day.fertile) classes.push("fertile");
      if (day.ovulation) classes.push("ovulation");
      if (day.is_today) classes.push("is-today");
      cells.push(
        `<button type="button" class="${classes.join(" ")}" data-date="${day.date}" aria-label="${day.date}">${day.day}</button>`
      );
    }
    $("#calendarGrid").innerHTML = cells.join("");
  }

  async function submitPeriod(event) {
    event.preventDefault();
    const payload = {
      start_date: $("#periodStart").value,
      end_date: $("#periodEnd").value || null,
      flow: state.flow,
      symptoms: $("#periodSymptoms").value.trim(),
      notes: $("#periodNotes").value.trim(),
    };
    if (!payload.start_date) {
      toast("请选择开始日期");
      return;
    }
    try {
      if (state.periodEditingId) {
        await request(`/api/cycle/periods/${state.periodEditingId}`, {
          method: "PUT",
          json: payload,
        });
        toast("已更新经期记录");
      } else {
        await request("/api/cycle/periods", { method: "POST", json: payload });
        toast("已记录，正在更新预测");
      }
      closePeriodRecordPanel();
      await loadOverview();
      await loadCalendar(state.calendarYear, state.calendarMonth);
      renderMode();
    } catch (error) {
      toast(error.message);
    }
  }

  function resetPeriodForm() {
    state.periodEditingId = null;
    $("#periodForm").reset();
    $("#periodStart").value = todayISO();
    $("#periodEnd").value = "";
    $("#periodSymptoms").value = "";
    $("#periodNotes").value = "";
    state.flow = "medium";
    setSegmented("#flowSegmented", "medium");
    $("#periodFormTitle").textContent = "记录月经";
  }

  function openPeriodRecordPanel() {
    resetPeriodForm();
    $("#periodFormCard").classList.remove("hidden");
    $("#periodFormCard").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function closePeriodRecordPanel() {
    resetPeriodForm();
    $("#periodFormCard").classList.add("hidden");
  }

  function renderPeriodHistory() {
    const root = $("#periodHistory");
    if (!root) return;
    const items = state.overview?.history || [];
    $("#periodCount").textContent = items.length ? `${items.length} 条` : "";
    if (!items.length) {
      root.innerHTML = '<div class="empty-state">还没有记录。记录一次月经即可开始预测。</div>';
      return;
    }
    root.innerHTML = items
      .map((item) => {
        const days = item.period_length ? `${item.period_length} 天` : "未填结束";
        const cycle = item.cycle_length ? ` · 周期 ${item.cycle_length} 天` : "";
        return `
          <div class="list-item" data-id="${item.id}">
            <div class="icon-badge">${item.period_length || "经"}</div>
            <div class="item-main">
              <div class="item-title">
                ${fmtCN(item.start_date)}${item.end_date ? ` - ${fmtCN(item.end_date)}` : ""}
                <span class="tag">${esc(FLOW_LABELS[item.flow] || "量中")}</span>
              </div>
              <div class="item-sub">${days}${cycle}${item.symptoms ? ` · ${esc(item.symptoms)}` : ""}${item.notes ? ` · ${esc(item.notes)}` : ""}</div>
            </div>
            <div class="item-actions">
              <button type="button" class="link-btn" data-action="edit">编辑</button>
              <button type="button" class="danger-link" data-action="delete">删除</button>
            </div>
          </div>`;
      })
      .join("");
  }

  function renderPredictionDetail() {
    const root = $("#predictionDetail");
    if (!root) return;
    const method = $("#predictionMethod");
    const overview = state.overview;
    if (!overview || !overview.has_data) {
      if (method) method.textContent = "";
      root.innerHTML = '<div class="empty-state">记录经期后显示拟合结果</div>';
      return;
    }
    const prediction = overview.prediction || {};
    if (method) {
      method.textContent =
        prediction.fit_method === "linear_fit" ? "基于最近周期线性拟合" : "默认周期估算";
    }
    const windowStart = prediction.prediction_window_start;
    const windowEnd = prediction.prediction_window_end;
    const windowText = windowStart && windowEnd ? fmtRange(windowStart, windowEnd) : "—";
    const rangeText =
      prediction.cycle_range_min != null && prediction.cycle_range_max != null
        ? `${prediction.cycle_range_min}-${prediction.cycle_range_max} 天`
        : "—";
    const irregular = Boolean(prediction.irregular);
    const trendLabel = prediction.cycle_trend_label || "趋势未知";

    root.innerHTML = `
      <div class="grid-2 prediction-grid">
        <div class="stat-card">
          <span class="stat-label">拟合预测周期</span>
          <div>
            <div class="stat-value">${prediction.predicted_cycle_length || prediction.average_cycle_length}<small>天</small></div>
            <div class="stat-sub">平均 ${prediction.average_cycle_length} 天 · 中位 ${prediction.median_cycle_length} 天</div>
          </div>
        </div>
        <div class="stat-card">
          <span class="stat-label">周期波动</span>
          <div>
            <div class="stat-value">±${prediction.cycle_variability}<small>天</small></div>
            <div class="stat-sub">最近周期范围 ${rangeText}</div>
          </div>
        </div>
        <div class="stat-card">
          <span class="stat-label">预测窗口</span>
          <div>
            <div class="stat-value">${windowText}</div>
            <div class="stat-sub">拟合值 ${fmtCN(prediction.next_period_start)} ± ${prediction.prediction_window_days || 1} 天</div>
          </div>
        </div>
        <div class="stat-card">
          <span class="stat-label">周期趋势</span>
          <div>
            <div class="stat-value">${esc(trendLabel)}</div>
            <div class="stat-sub">基于 ${prediction.cycles_used} 个周期的拟合</div>
          </div>
        </div>
      </div>
      <div class="chips">
        <span class="tag ${irregular ? "tag--gold" : "tag--mint"}">${irregular ? "周期波动较大" : "周期较稳定"}</span>
        <span class="tag">可信度 ${esc(prediction.confidence_label || "—")}</span>
        <span class="tag">拟合残差 ±${prediction.residual_std != null ? prediction.residual_std : 0} 天</span>
      </div>
      ${
        irregular
          ? `<div class="tip-box"><b>关于不稳定周期</b><div>系统已用最近周期的线性趋势拟合下次经期，并给出预测窗口而不是单一日期。若周期长期不规律或伴随异常出血，建议咨询专业医生。</div></div>`
          : ""
      }`;
  }

  function startEditPeriod(id) {
    const item = (state.overview?.history || []).find((entry) => entry.id === id);
    if (!item) return;
    state.periodEditingId = id;
    $("#periodStart").value = item.start_date;
    $("#periodEnd").value = item.end_date || "";
    state.flow = item.flow || "medium";
    setSegmented("#flowSegmented", state.flow);
    $("#periodSymptoms").value = item.symptoms || "";
    $("#periodNotes").value = item.notes || "";
    $("#periodFormTitle").textContent = "编辑经期记录";
    $("#periodFormCard").classList.remove("hidden");
    $("#periodFormCard").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function deletePeriod(id) {
    if (!window.confirm("确定删除这条经期记录吗？")) return;
    try {
      await request(`/api/cycle/periods/${id}`, { method: "DELETE" });
      if (state.periodEditingId === id) closePeriodRecordPanel();
      toast("已删除");
      await loadOverview();
      await loadCalendar(state.calendarYear, state.calendarMonth);
    } catch (error) {
      toast(error.message);
    }
  }

  /* ---------------- 饮食 ---------------- */

  function bindDiet() {
    $("#dietDailyDate").addEventListener("change", () => loadDietDaily());
    $("#dietRecommend").addEventListener("click", recommendDiet);
    $("#dietPhoto").addEventListener("change", () => {
      const file = $("#dietPhoto").files[0];
      const preview = $("#dietPreview");
      const placeholder = $("#photoPlaceholder");
      if (!file) {
        resetPhoto();
        return;
      }
      preview.src = URL.createObjectURL(file);
      preview.classList.remove("hidden");
      placeholder.classList.add("hidden");
    });
    $("#dietForm").addEventListener("submit", submitDiet);
    $("#dietHistory").addEventListener("click", (event) => {
      const button = event.target.closest("[data-action]");
      if (!button) return;
      const item = button.closest(".list-item");
      const id = Number(item.dataset.id);
      if (button.dataset.action === "view") viewDietLog(id);
      if (button.dataset.action === "delete") deleteDietLog(id);
    });
  }

  function resetPhoto() {
    $("#dietPhoto").value = "";
    const preview = $("#dietPreview");
    preview.src = "";
    preview.classList.add("hidden");
    $("#photoPlaceholder").classList.remove("hidden");
  }

  async function submitDiet(event) {
    event.preventDefault();
    const description = $("#dietDescription").value.trim();
    const file = $("#dietPhoto").files[0];
    if (description.length < 2 && !file) {
      toast("请拍照或描述一下吃了什么");
      return;
    }
    const form = new FormData();
    form.append("description", description);
    form.append("meal_type", state.mealType);
    form.append("log_date", $("#dietDailyDate").value || todayISO());
    if (file) form.append("photo", file);

    const button = $("#dietSubmit");
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "正在估算…";
    showLoading(
      file ? "正在识别照片并估算营养…" : "正在估算营养…"
    );
    try {
      const record = await request("/api/diet/analyze", { method: "POST", form });
      renderDietResult(record);
      $("#dietDescription").value = "";
      resetPhoto();
      await Promise.all([loadDietHistory(), loadDietDaily()]);
      toast("营养分析完成");
      $("#dietResult").scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
      toast(error.message);
    } finally {
      hideLoading();
      button.disabled = false;
      button.textContent = original;
    }
  }

  function renderDietResult(record) {
    const totals = {
      calories: parseNum(record.calories),
      protein: parseNum(record.protein),
      fat: parseNum(record.fat),
      carbs: parseNum(record.carbs),
      fiber: parseNum(record.fiber),
      sugar: parseNum(record.sugar),
      sodium: parseNum(record.sodium),
    };
    const macroCalories = totals.protein * 4 + totals.fat * 9 + totals.carbs * 4;
    const ratio = (grams, factor) =>
      macroCalories > 0 ? Math.round(((grams * factor) / macroCalories) * 100) : 0;

    const proteinPct = ratio(totals.protein, 4);
    const fatPct = ratio(totals.fat, 9);
    const carbsPct = ratio(totals.carbs, 4);
    const score = Math.max(0, Math.min(100, Math.round(parseNum(record.score))));

    const advice = Array.isArray(record.advice) ? record.advice : [];
    const tips = Array.isArray(record.tips) ? record.tips : [];
    const foods = Array.isArray(record.foods) ? record.foods : [];
    const photo = record.photo_url
      ? `<img src="${esc(record.photo_url)}" alt="餐食照片" style="width:100%;max-height:180px;object-fit:cover;border-radius:14px;margin-bottom:12px;">`
      : "";
    const visionChip = record.vision_used
      ? '<span class="chip chip--mint">AI 已识别照片</span>'
      : record.photo_url
        ? '<span class="chip chip--gold">照片已留档</span>'
        : "";

    $("#dietResult").innerHTML = `
      <div class="result-card">
        <div class="result-head">
          <div>
            <span class="meal-label">${esc(MEAL_LABELS[record.meal_type] || "用餐")} · ${esc(record.log_date || "")}</span>
            <h3>${Math.round(totals.calories)} <small>千卡</small></h3>
          </div>
          <div class="score-badge" style="--score:${score}"><span>${score}<small>健康分</small></span></div>
        </div>
        ${photo}
        <div class="macros">
          <div class="macro macro--p">
            <span>蛋白质</span>
            <div class="macro-bar"><span style="width:${clampPercent(totals.protein / 50 * 100)}%"></span></div>
            <span class="macro-value"><strong>${totals.protein}g</strong> · ${proteinPct}%</span>
          </div>
          <div class="macro macro--f">
            <span>脂肪</span>
            <div class="macro-bar"><span style="width:${clampPercent(totals.fat / 70 * 100)}%"></span></div>
            <span class="macro-value"><strong>${totals.fat}g</strong> · ${fatPct}%</span>
          </div>
          <div class="macro macro--c">
            <span>碳水</span>
            <div class="macro-bar"><span style="width:${clampPercent(totals.carbs / 120 * 100)}%"></span></div>
            <span class="macro-value"><strong>${totals.carbs}g</strong> · ${carbsPct}%</span>
          </div>
        </div>
        <div class="nutrient-chips">
          ${visionChip}
          <span class="chip">膳食纤维 ${totals.fiber}g</span>
          <span class="chip">糖 ${totals.sugar}g</span>
          <span class="chip">钠 ${Math.round(totals.sodium)}mg</span>
        </div>
        ${
          foods.length
            ? `<div class="food-list">${foods
                .map(
                  (food) =>
                    `<div class="food-row"><span>${esc(food.name)}${food.portion ? ` · ${esc(food.portion)}` : ""}</span><strong>${Math.round(parseNum(food.calories))} 千卡</strong></div>`
                )
                .join("")}</div>`
            : ""
        }
        ${
          advice.length
            ? `<ul class="advice-list">${advice.map((text) => `<li>${esc(text)}</li>`).join("")}</ul>`
            : ""
        }
        ${
          tips.length
            ? `<div class="tip-box"><b>今日小贴士</b>${tips.map((text) => `<div>${esc(text)}</div>`).join("")}</div>`
            : ""
        }
        <p class="disclaimer">${esc(record.note || "营养数据为基于文字描述的估算，仅供参考，不构成医疗建议。")}</p>
      </div>`;
  }

  async function loadDietHistory() {
    try {
      const data = await request("/api/diet/logs?limit=20");
      state.dietHistory = data.items || [];
      renderDietHistory();
    } catch (error) {
      toast(error.message);
    }
  }

  function renderDietHistory() {
    const root = $("#dietHistory");
    if (!root) return;
    const items = state.dietHistory;
    if (!items.length) {
      root.innerHTML = '<div class="empty-state">还没有饮食记录，上传一张照片并描述这一餐吧。</div>';
      return;
    }
    root.innerHTML = items
      .map((item) => {
        const badge = item.photo_url
          ? `<div class="icon-badge"><img src="${esc(item.photo_url)}" alt=""></div>`
          : `<div class="icon-badge">${esc(MEAL_SHORT[item.meal_type] || "餐")}</div>`;
        return `
          <div class="list-item" data-id="${item.id}">
            ${badge}
            <div class="item-main">
              <div class="item-title">${esc(item.description || "照片记录")}</div>
              <div class="item-sub">${esc(item.log_date)} · ${esc(MEAL_LABELS[item.meal_type] || "用餐")} · ${Math.round(parseNum(item.calories))} 千卡${item.photo_url ? " · 含照片" : ""}</div>
            </div>
            <div class="item-actions">
              <button type="button" class="link-btn" data-action="view">查看</button>
              <button type="button" class="danger-link" data-action="delete">删除</button>
            </div>
          </div>`;
      })
      .join("");
  }

  function viewDietLog(id) {
    const record = state.dietHistory.find((item) => item.id === id);
    if (!record) return;
    renderDietResult(record);
    $("#dietResult").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function deleteDietLog(id) {
    if (!window.confirm("确定删除这条饮食记录吗？")) return;
    try {
      await request(`/api/diet/logs/${id}`, { method: "DELETE" });
      toast("已删除");
      await loadDietHistory();
    } catch (error) {
      toast(error.message);
    }
  }

  async function loadDietDaily() {
    const input = $("#dietDailyDate");
    const selected = input?.value || state.dietDate || todayISO();
    state.dietDate = selected;
    try {
      const data = await request(`/api/diet/daily?date=${encodeURIComponent(selected)}`);
      state.dietDaily = data;
      renderDietDaily(data);
    } catch (error) {
      toast(error.message);
    }
  }

  function renderDietDaily(data) {
    const root = $("#dietDailySummary");
    if (!root) return;
    if (!data) {
      root.innerHTML = '<div class="empty-state">还没有今日数据</div>';
      return;
    }
    const totals = data.totals || {};
    const target = data.target || {};
    const remaining = data.remaining || {};
    const exercise = (data.exercise || {}).today || {};
    const progress = clampPercent((Number(data.progress) || 0) * 100);
    const over = Number(remaining.calories) < 0;
    const mealChips = (data.meals || [])
      .map(
        (meal) =>
          `<span class="chip">${esc(meal.label)} ${Math.round(parseNum(meal.calories))} 千卡</span>`
      )
      .join("");
    const macroChips = `
      <span class="chip">蛋白 ${Math.round(parseNum(totals.protein))}/${target.protein || "—"}g</span>
      <span class="chip">脂肪 ${Math.round(parseNum(totals.fat))}/${target.fat || "—"}g</span>
      <span class="chip">碳水 ${Math.round(parseNum(totals.carbs))}/${target.carbs || "—"}g</span>
      <span class="chip">纤维 ${Math.round(parseNum(totals.fiber))}g</span>`;
    const balance = data.energy_balance || {};
    const exerciseEstimated = Math.round(
      parseNum(balance.exercise_estimated_calories)
    );
    const deficit = Math.round(parseNum(balance.deficit));
    const deficitText =
      deficit > 0
        ? `热量缺口 ${deficit} 千卡`
        : deficit < 0
          ? `热量盈余 ${-deficit} 千卡`
          : "热量基本平衡";
    const suggestions = Array.isArray(data.suggestions) ? data.suggestions : [];

    root.innerHTML = `
      <div class="grid-2">
        <div class="stat-card">
          <span class="stat-label">已摄入</span>
          <div>
            <div class="stat-value">${Math.round(parseNum(totals.calories))}<small>千卡</small></div>
            <div class="stat-sub">目标 ${target.calories || "—"} 千卡 · ${esc(data.status_label || "")}</div>
          </div>
        </div>
        <div class="stat-card">
          <span class="stat-label">${over ? "已超出" : "剩余额度"}</span>
          <div>
            <div class="stat-value">${Math.abs(Math.round(parseNum(remaining.calories)))}<small>千卡</small></div>
            <div class="stat-sub">蛋白 ${Math.round(parseNum(totals.protein))}/${target.protein || "—"}g · 脂肪 ${Math.round(parseNum(totals.fat))}/${target.fat || "—"}g</div>
          </div>
        </div>
      </div>
      <div class="calorie-track ${over ? "is-over" : ""}">
        <span style="width:${progress}%"></span>
      </div>
      <div class="energy-balance ${balance.status === "surplus" ? "is-surplus" : ""}">
        <span>${esc(deficitText)}</span>
        <small>总消耗 ${Math.round(parseNum(balance.total_burn))} 千卡 · 运动额外 ${Math.round(parseNum(balance.exercise_calories))} 千卡${exerciseEstimated ? `（估算 ${exerciseEstimated}）` : ""}</small>
      </div>
      <div class="chips">
        ${macroChips}
        ${mealChips}
        <span class="chip chip--mint">今日运动 ${Math.round(parseNum(exercise.duration_min))} 分钟 · ${Math.round(parseNum(exercise.calories))} 千卡${exerciseEstimated ? `（估算 ${exerciseEstimated}）` : ""}</span>
      </div>
      ${
        suggestions.length
          ? `<ul class="advice-list">${suggestions.map((text) => `<li>${esc(text)}</li>`).join("")}</ul>`
          : ""
      }`;
  }

  async function recommendDiet() {
    const button = $("#dietRecommend");
    const original = button.textContent;
    const selected = $("#dietDailyDate").value || state.dietDate || todayISO();
    button.disabled = true;
    button.textContent = "正在生成推荐…";
    showLoading("正在生成推荐…");
    try {
      const data = await request("/api/diet/recommend", {
        method: "POST",
        json: { date: selected },
      });
      renderMealRecommendation(data);
      toast("已生成下一餐与运动推荐");
    } catch (error) {
      toast(error.message);
    } finally {
      hideLoading();
      button.disabled = false;
      button.textContent = original;
    }
  }

  function renderMealRecommendation(data) {
    const root = $("#dietRecommendResult");
    if (!root) return;
    const rec = data.recommendation || {};
    const dishes = Array.isArray(rec.dishes) ? rec.dishes : [];
    const exercises = Array.isArray(rec.exercise) ? rec.exercise : [];
    const tips = Array.isArray(rec.meal_tips) ? rec.meal_tips : [];

    root.innerHTML = `
      <div class="result-card">
        <div class="result-head">
          <div>
            <span class="meal-label">推荐${esc(data.meal_label || "下一餐")}</span>
            <h3>${rec.target_calories || 0} <small>千卡建议</small></h3>
          </div>
        </div>
        <p class="muted">${esc(rec.summary || "")}</p>
        <div class="food-list">
          ${dishes
            .map(
              (dish) => `
              <div class="food-row">
                <span>${esc(dish.name)}${dish.portion ? ` · ${esc(dish.portion)}` : ""}${dish.reason ? `<small class="dish-reason">${esc(dish.reason)}</small>` : ""}</span>
                <strong>${Math.round(parseNum(dish.calories))} 千卡</strong>
              </div>`
            )
            .join("")}
        </div>
        ${
          tips.length
            ? `<div class="tip-box"><b>搭配建议</b>${tips.map((text) => `<div>${esc(text)}</div>`).join("")}</div>`
            : ""
        }
        <div class="plan-section-title">今日还可以这样运动</div>
        <div class="plan-list">
          ${exercises
            .map((item) => {
              const intensity = item.intensity || "moderate";
              const label = INTENSITY_LABELS[intensity] || "中强度";
              const tagClass = intensity === "low" ? "tag--mint" : intensity === "high" ? "" : "tag--gold";
              return `
                <div class="plan-day">
                  <div class="day-badge">${item.duration_min || 20}′</div>
                  <div class="plan-main">
                    <div class="plan-title">${esc(item.name)} <span class="tag ${tagClass}">${label}</span></div>
                    <p>${esc(item.reason || "")}</p>
                  </div>
                </div>`;
            })
            .join("")}
        </div>
        ${rec.exercise_note ? `<p class="muted small">${esc(rec.exercise_note)}</p>` : ""}
        <p class="disclaimer">${esc(rec.note || "")}</p>
      </div>`;
    root.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  /* ---------------- 运动 ---------------- */

  function bindExercise() {
    $("#saveProfile").addEventListener("click", saveProfile);
    $("#generatePlan").addEventListener("click", generatePlan);
    $("#bodyForm").addEventListener("submit", submitBodyRecord);
    $("#exerciseDescribeForm").addEventListener("submit", submitExerciseDescription);
    $("#analyzeExerciseShot").addEventListener("click", analyzeExerciseShot);
    $("#exerciseShot").addEventListener("change", () => {
      const file = $("#exerciseShot").files[0];
      const preview = $("#exercisePreview");
      const placeholder = $("#exercisePhotoPlaceholder");
      if (!file) {
        resetExerciseShot();
        return;
      }
      preview.src = URL.createObjectURL(file);
      preview.classList.remove("hidden");
      placeholder.classList.add("hidden");
    });
    $("#exerciseLogHistory").addEventListener("click", (event) => {
      const action = event.target.closest("[data-action='delete']");
      if (!action) return;
      const id = Number(action.closest(".list-item").dataset.id);
      deleteExerciseLog(id);
    });
    $("#bodyHistory").addEventListener("click", (event) => {
      const action = event.target.closest("[data-action='delete']");
      if (!action) return;
      const id = Number(action.closest(".list-item").dataset.id);
      deleteBodyRecord(id);
    });
  }

  function resetExerciseShot() {
    $("#exerciseShot").value = "";
    $("#exerciseShotNote").value = "";
    const preview = $("#exercisePreview");
    preview.src = "";
    preview.classList.add("hidden");
    $("#exercisePhotoPlaceholder").classList.remove("hidden");
  }

  function fillProfileForm() {
    const profile = state.profile;
    if (!profile) return;
    $("#profileBirthYear").value = profile.birth_year || "";
    $("#profileHeight").value = profile.height_cm || "";
    $("#profileWeight").value = profile.weight_kg || "";
    $("#profileActivity").value = profile.activity_level || "light";
    $("#profileGoal").value = profile.goal || "maintain";
    $("#profileTargetWeight").value = profile.target_weight_kg || "";
    $("#profileTargetDate").value = profile.target_date || "";
    $("#profileInjuries").value = profile.injuries || "";
  }

  function renderMetricsChips() {
    const root = $("#metricsChips");
    if (!root) return;
    const metrics = state.metrics || {};
    const chips = [];
    if (metrics.age) chips.push(`<span class="chip">${metrics.age} 岁</span>`);
    if (metrics.bmi) chips.push(`<span class="chip chip--gold">BMI ${metrics.bmi}</span>`);
    if (metrics.bmr) chips.push(`<span class="chip chip--mint">基础代谢 ${metrics.bmr} 千卡</span>`);
    if (metrics.tdee) chips.push(`<span class="chip">每日消耗约 ${metrics.tdee} 千卡</span>`);
    if (!chips.length) {
      chips.push('<span class="chip">填写身高、体重和出生年份后显示代谢数据</span>');
    }
    root.innerHTML = chips.join("");
  }

  function renderGoalPlan() {
    const root = $("#goalPlan");
    if (!root) return;
    const plan = (state.metrics || {}).goal_plan || {};
    if (!plan.has_target) {
      root.innerHTML = '<div class="goal-plan-empty">设置目标体重和期望完成日期后，自动计算每日热量缺口或盈余。</div>';
      return;
    }
    if (!plan.days_left || plan.days_left <= 0) {
      root.innerHTML = `<div class="goal-plan-warn">${esc(plan.warning || "请设置未来的期望完成日期。")}</div>`;
      return;
    }
    const mode = plan.mode || "maintain";
    const change = Math.abs(parseNum(plan.weight_diff_kg)).toFixed(1);
    const weekly = Math.abs(parseNum(plan.weekly_change_kg)).toFixed(2);
    const delta = Math.abs(Math.round(parseNum(plan.daily_energy_delta)));
    const targetText =
      mode === "lose"
        ? `每日热量缺口 ${delta} 千卡`
        : mode === "gain"
          ? `每日热量盈余 ${delta} 千卡`
          : "维持当前体重";
    root.innerHTML = `
      <div class="goal-plan-grid">
        <div><span>当前 → 目标</span><b>${parseNum(plan.current_weight_kg).toFixed(1)} → ${parseNum(plan.target_weight_kg).toFixed(1)} kg</b></div>
        <div><span>还需${mode === "gain" ? "增重" : "减重"}</span><b>${change} kg</b></div>
        <div><span>剩余时间</span><b>${plan.days_left} 天</b></div>
        <div><span>每周变化</span><b>${weekly} kg</b></div>
      </div>
      <div class="goal-plan-delta ${plan.too_aggressive ? "is-warn" : ""}">
        <strong>${targetText}</strong>
        <small>按 1 kg 脂肪 ≈ 7700 千卡估算，实际会受水分和运动影响</small>
      </div>
      ${plan.warning ? `<div class="goal-plan-warn">${esc(plan.warning)}</div>` : ""}`;
  }

  async function saveProfile() {
    const birthYear = $("#profileBirthYear").value;
    const height = $("#profileHeight").value;
    const weight = $("#profileWeight").value;
    const payload = {
      birth_year: birthYear ? Number(birthYear) : null,
      height_cm: height ? Number(height) : null,
      weight_kg: weight ? Number(weight) : null,
      activity_level: $("#profileActivity").value,
      goal: $("#profileGoal").value,
      target_weight_kg: $("#profileTargetWeight").value
        ? Number($("#profileTargetWeight").value)
        : null,
      target_date: $("#profileTargetDate").value || null,
      injuries: $("#profileInjuries").value.trim(),
    };
    const button = $("#saveProfile");
    button.disabled = true;
    try {
      const data = await request("/api/profile", { method: "PUT", json: payload });
      state.profile = data.profile;
      state.metrics = data.metrics;
      renderProfileSnapshot();
      renderMetricsChips();
      renderGoalPlan();
      fillProfileForm();
      toast("身体档案已保存");
    } catch (error) {
      toast(error.message);
    } finally {
      button.disabled = false;
    }
  }

  function renderExercisePhase() {
    const current = state.overview?.current;
    if (!current || !state.overview?.has_data) {
      $("#exercisePhase").textContent = "记录月经后更精准";
      return;
    }
    $("#exercisePhase").textContent = `${current.phase_label} · 周期第 ${current.cycle_day} 天`;
  }

  async function generatePlan() {
    const button = $("#generatePlan");
    const original = button.textContent;
    const preferences = $("#exercisePlanPreferences").value.trim();
    button.disabled = true;
    button.textContent = "正在生成…";
    showLoading(
      preferences ? "DeepSeek 正在按你的条件生成计划…" : "正在生成运动计划…"
    );
    try {
      const data = await request("/api/exercise/plan", {
        method: "POST",
        json: { preferences },
      });
      state.exercisePlan = data;
      renderExercisePlan(data);
      await loadHomeToday();
      toast(preferences ? "已按你的条件生成运动计划" : "运动计划已生成");
    } catch (error) {
      toast(error.message);
    } finally {
      hideLoading();
      button.disabled = false;
      button.textContent = original;
    }
  }

  async function loadLatestPlan() {
    try {
      const data = await request("/api/exercise/plans?limit=1");
      const latest = data.items?.[0];
      if (latest && latest.plan) {
        state.exercisePlan = latest;
        renderExercisePlan(latest);
      } else {
        renderExercisePhase();
      }
    } catch (error) {
      /* 忽略历史计划加载失败 */
    }
  }

  function renderExercisePlan(data) {
    const plan = data.plan || {};
    const weekly = Array.isArray(plan.weekly_plan) ? plan.weekly_plan : [];
    const nutrition = Array.isArray(plan.nutrition_tips) ? plan.nutrition_tips : [];
    const cautions = Array.isArray(plan.cautions) ? plan.cautions : [];
    const metrics = data.metrics || state.metrics || {};
    const created = data.created_at ? `<span class="hint">生成于 ${esc(data.created_at.slice(0, 16))}</span>` : "";

    const chips = [];
    if (data.phase_label) chips.push(`<span class="chip">${esc(data.phase_label)}</span>`);
    if (metrics.bmi) chips.push(`<span class="chip chip--gold">BMI ${metrics.bmi}</span>`);
    if (metrics.tdee) chips.push(`<span class="chip chip--mint">TDEE ${metrics.tdee} 千卡</span>`);


    const preferences = plan.preferences || data.preferences || "";
    if (preferences) {
      chips.push(`<span class="chip">条件：${esc(preferences)}</span>`);
    }

    $("#exerciseResult").innerHTML = `
      <div class="exercise-head">
        <h3>${esc(plan.summary || "本周训练计划")}</h3>
        <p>${esc(plan.phase_note || "")}</p>
        <div class="chips">${chips.join("")} ${created}</div>
      </div>
      <div class="plan-list">
        ${weekly
          .map((day) => {
            const intensity = day.intensity || "moderate";
            const intensityLabel = INTENSITY_LABELS[intensity] || "中强度";
            const tagClass = intensity === "low" ? "tag--mint" : intensity === "high" ? "" : "tag--gold";
            return `
              <div class="plan-day">
                <div class="day-badge">${esc(day.day || "")}</div>
                <div class="plan-main">
                  <div class="plan-title">
                    ${esc(day.focus || "训练")}
                    <span class="tag ${tagClass}">${intensityLabel}</span>
                    <small>${day.duration_min || 30} 分钟</small>
                  </div>
                  <p>${esc(day.workout || "")}</p>
                  ${day.notes ? `<p>${esc(day.notes)}</p>` : ""}
                </div>
              </div>`;
          })
          .join("")}
      </div>
      ${
        nutrition.length
          ? `<div class="plan-section-title">营养提示</div><div class="tip-box">${nutrition.map((text) => `<div>${esc(text)}</div>`).join("")}</div>`
          : ""
      }
      ${
        cautions.length
          ? `<div class="plan-section-title">注意事项</div><ul class="advice-list">${cautions.map((text) => `<li>${esc(text)}</li>`).join("")}</ul>`
          : ""
      }`;
  }

  async function loadExerciseLogs() {
    try {
      const data = await request("/api/exercise/logs?limit=30");
      state.exerciseLogs = data.items || [];
      renderExerciseLogs();
    } catch (error) {
      toast(error.message);
    }
  }

  function renderExerciseLogs() {
    const root = $("#exerciseLogHistory");
    if (!root) return;
    const items = state.exerciseLogs;
    $("#exerciseLogCount").textContent = items.length ? `${items.length} 条` : "";
    if (!items.length) {
      root.innerHTML = '<div class="empty-state">还没有运动记录，上传一张截图或导入手环数据吧。</div>';
      return;
    }
    root.innerHTML = items
      .map((item) => {
        const badge = item.photo_url
          ? `<div class="icon-badge"><img src="${esc(item.photo_url)}" alt=""></div>`
          : `<div class="icon-badge">${esc((item.activity || "运动")[0])}</div>`;
        const meta = [];
        if (item.start_time) meta.push(item.start_time);
        if (item.duration_min) meta.push(`${Math.round(parseNum(item.duration_min))} 分钟`);
        if (item.calories) meta.push(`${Math.round(parseNum(item.calories))} 千卡`);
        if (item.distance_km) meta.push(`${parseNum(item.distance_km).toFixed(1)} km`);
        if (item.steps) meta.push(`${Math.round(parseNum(item.steps))} 步`);
        if (item.avg_heart_rate) meta.push(`${item.avg_heart_rate} 次/分`);
        const estimatedTag = item.calories_estimated
          ? '<span class="tag tag--gold">热量估算</span>'
          : "";
        return `
          <div class="list-item" data-id="${item.id}">
            ${badge}
            <div class="item-main">
              <div class="item-title">
                ${esc(item.activity || "运动")}
                <span class="tag">${esc(item.source_label || "手动")}</span>
                ${estimatedTag}
              </div>
              <div class="item-sub">${esc(item.log_date)}${meta.length ? ` · ${meta.join(" · ")}` : ""}${item.notes ? ` · ${esc(item.notes)}` : ""}</div>
              ${item.calorie_basis ? `<div class="item-sub">${esc(item.calorie_basis)}</div>` : ""}
            </div>
            <div class="item-actions">
              <button type="button" class="danger-link" data-action="delete">删除</button>
            </div>
          </div>`;
      })
      .join("");
  }

  async function loadExerciseSummary() {
    try {
      state.exerciseSummary = await request("/api/exercise/summary?days=30");
      renderExerciseSummary();
    } catch (error) {
      /* 忽略统计失败，不影响记录展示 */
    }
  }

  function renderExerciseSummary() {
    const root = $("#exerciseActivitySummary");
    if (!root) return;
    const data = state.exerciseSummary;
    if (!data) {
      root.innerHTML = "";
      return;
    }
    const chips = [
      `<span class="chip">近 ${data.days} 天 ${data.sessions} 次运动</span>`,
      `<span class="chip chip--mint">活跃 ${data.active_days} 天</span>`,
      `<span class="chip chip--gold">${Math.round(parseNum(data.total_duration_min))} 分钟</span>`,
    ];
    if (data.total_calories) {
      chips.push(`<span class="chip">消耗 ${Math.round(parseNum(data.total_calories))} 千卡</span>`);
    }
    if (data.estimated_calories) {
      chips.push(
        `<span class="chip chip--gold">其中估算 ${Math.round(parseNum(data.estimated_calories))} 千卡</span>`
      );
    }
    const suggestion = (data.suggestions || [])[0];
    root.innerHTML = `
      <div class="chips">${chips.join("")}</div>
      ${suggestion ? `<div class="tip-box"><b>运动建议</b><div>${esc(suggestion)}</div></div>` : ""}`;
  }

  async function analyzeExerciseShot() {
    const file = $("#exerciseShot").files[0];
    if (!file) {
      toast("请先选择一张运动截图");
      return;
    }
    const button = $("#analyzeExerciseShot");
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "正在识别…";
    showLoading("正在识别运动截图…");
    const form = new FormData();
    form.append("photo", file);
    form.append("note", $("#exerciseShotNote").value.trim());
    try {
      const data = await request("/api/exercise/logs/analyze", {
        method: "POST",
        form,
      });
      renderExerciseLogResult(data, "screenshot");
      resetExerciseShot();
      await Promise.all([loadExerciseLogs(), loadExerciseSummary()]);
      const estimated = Math.round(parseNum(data.estimated_calories));
      toast(estimated ? `已识别并保存，估算消耗约 ${estimated} 千卡` : "已识别并保存运动记录");
      $("#exerciseShotResultDetails").scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    } catch (error) {
      toast(error.message);
    } finally {
      hideLoading();
      button.disabled = false;
      button.textContent = original;
    }
  }

  async function submitExerciseDescription(event) {
    event.preventDefault();
    const description = $("#exerciseDescribeText").value.trim();
    if (description.length < 2) {
      toast("请描述一下今天的运动情况");
      return;
    }
    const button = $("#exerciseDescribeSubmit");
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "正在解析…";
    showLoading("DeepSeek 正在解析运动描述…");
    try {
      const data = await request("/api/exercise/logs/describe", {
        method: "POST",
        json: {
          description,
          log_date: $("#exerciseDescribeDate").value || todayISO(),
        },
      });
      renderExerciseLogResult(data, "description");
      $("#exerciseDescribeText").value = "";
      await Promise.all([loadExerciseLogs(), loadExerciseSummary()]);
      const estimated = Math.round(parseNum(data.estimated_calories));
      toast(
        estimated
          ? `已记录，估算消耗约 ${estimated} 千卡，已计入今日热量`
          : "已保存运动记录"
      );
      $("#exerciseDescribeResultDetails").scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    } catch (error) {
      toast(error.message);
    } finally {
      hideLoading();
      button.disabled = false;
      button.textContent = original;
    }
  }

  function renderExerciseLogResult(data, kind = "screenshot") {
    const records = Array.isArray(data.records) ? data.records : [];
    const isDescription = kind === "description";
    const photo = data.photo_url
      ? `<img src="${esc(data.photo_url)}" alt="运动记录截图" style="width:100%;max-height:200px;object-fit:cover;border-radius:14px;margin-bottom:12px;">`
      : "";
    const rows = records
      .map((record) => {
        const meta = [];
        if (record.log_date) meta.push(record.log_date);
        if (record.start_time) meta.push(record.start_time);
        if (record.duration_min) meta.push(`${Math.round(parseNum(record.duration_min))} 分钟`);
        if (record.calories) meta.push(`${Math.round(parseNum(record.calories))} 千卡`);
        if (record.distance_km) meta.push(`${parseNum(record.distance_km).toFixed(1)} km`);
        if (record.steps) meta.push(`${Math.round(parseNum(record.steps))} 步`);
        if (record.avg_heart_rate) meta.push(`${record.avg_heart_rate} 次/分`);
        const estimateTag = record.calories_estimated
          ? ' <span class="tag tag--gold">热量估算</span>'
          : "";
        return `
          <div class="food-row">
            <span>
              ${esc(record.activity || "运动")} · ${meta.join(" · ")}
              ${estimateTag}
              ${record.calorie_basis ? `<small class="dish-reason">${esc(record.calorie_basis)}</small>` : ""}
            </span>
            <strong>已保存</strong>
          </div>`;
      })
      .join("");
    const estimatedChips = [];
    if (data.estimated_calories) {
      estimatedChips.push(
        `<span class="chip chip--gold">估算消耗 ${Math.round(parseNum(data.estimated_calories))} 千卡</span>`
      );
    }
    if (data.estimated_sessions) {
      estimatedChips.push(
        `<span class="chip">${data.estimated_sessions} 条记录为估算</span>`
      );
    }
    const targetId = isDescription
      ? "#exerciseDescribeResult"
      : "#exerciseLogResult";
    const detailsId = isDescription
      ? "#exerciseDescribeResultDetails"
      : "#exerciseShotResultDetails";
    const summaryId = isDescription
      ? "#exerciseDescribeResultSummary"
      : "#exerciseShotResultSummary";
    const details = $(detailsId);
    if (details) {
      details.classList.remove("hidden");
      details.hidden = false;
      details.open = false;
    }
    const summary = $(summaryId);
    if (summary) {
      const estimated = Math.round(parseNum(data.estimated_calories));
      summary.textContent = `${
        isDescription ? "查看解析结果" : "查看识别结果"
      } · ${records.length} 条${estimated ? ` · 估算 ${estimated} 千卡` : ""}`;
    }
    $(targetId).innerHTML = `
      <div class="result-card">
        <div class="result-head">
          <div>
            <span class="meal-label">${isDescription ? "文字解析" : "截图识别"}</span>
            <h3>${records.length} <small>条运动记录</small></h3>
          </div>
        </div>
        ${photo}
        ${estimatedChips.length ? `<div class="nutrient-chips">${estimatedChips.join("")}</div>` : ""}
        <div class="food-list">${rows}</div>
        <p class="disclaimer">${esc(data.note || data.summary || "")}</p>
      </div>`;
  }

  async function loadBodyData() {
    try {
      const [summary, records] = await Promise.all([
        request("/api/body/summary?days=180"),
        request("/api/body/records?limit=60"),
      ]);
      state.bodySummary = summary;
      state.bodyRecords = records.items || [];
      renderBodySummary();
      renderBodyHistory();
    } catch (error) {
      toast(error.message);
    }
  }

  function renderBodySummary() {
    const root = $("#bodySummary");
    if (!root) return;
    const data = state.bodySummary;
    const hint = $("#bodyTrendHint");
    if (!data) {
      root.innerHTML = "";
      if (hint) hint.textContent = "";
      return;
    }
    if (hint) hint.textContent = data.headline || "";
    const latest = data.latest || {};
    const weight = data.weight || {};
    const averages = data.averages || {};
    const chips = [];
    if (latest.weight_kg) chips.push(`<span class="chip">体重 ${latest.weight_kg} kg</span>`);
    if (latest.bmi) chips.push(`<span class="chip chip--gold">BMI ${latest.bmi} · ${esc(latest.bmi_category || "")}</span>`);
    if (latest.body_fat_pct) chips.push(`<span class="chip">体脂 ${latest.body_fat_pct}%</span>`);
    if (weight.weekly_change_kg != null) {
      chips.push(`<span class="chip chip--mint">每周 ${weight.weekly_change_kg > 0 ? "+" : ""}${weight.weekly_change_kg} kg · ${esc(weight.trend)}</span>`);
    }
    if (averages.sleep_hours != null) chips.push(`<span class="chip">睡眠 ${averages.sleep_hours} h</span>`);
    if (averages.steps != null) chips.push(`<span class="chip">步数 ${averages.steps}</span>`);
    if (averages.resting_hr != null) chips.push(`<span class="chip">静息心率 ${averages.resting_hr}</span>`);

    const chart = renderWeightChart(data.series || []);
    const suggestions = Array.isArray(data.suggestions) ? data.suggestions : [];
    root.innerHTML = `
      <div class="chips">${chips.join("")}</div>
      ${chart}
      ${
        suggestions.length
          ? `<ul class="advice-list">${suggestions.map((text) => `<li>${esc(text)}</li>`).join("")}</ul>`
          : ""
      }`;
  }

  function renderWeightChart(series) {
    const points = series.filter((item) => item.weight_kg != null);
    if (points.length < 2) {
      return '<div class="empty-state">记录至少 2 次体重后显示趋势图。</div>';
    }
    const width = 320;
    const height = 110;
    const pad = 12;
    const values = points.map((item) => parseNum(item.weight_kg));
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1;
    const xs = points.map((_, index) => pad + ((width - pad * 2) * index) / (points.length - 1));
    const ys = values.map((value) => pad + (height - pad * 2) * (1 - (value - min) / span));
    const line = xs
      .map((x, index) => `${index ? "L" : "M"}${x.toFixed(1)},${ys[index].toFixed(1)}`)
      .join(" ");
    const area = `${line} L${xs[xs.length - 1].toFixed(1)},${height - pad} L${xs[0].toFixed(1)},${height - pad} Z`;
    const dots = points
      .map(
        (item, index) =>
          `<circle cx="${xs[index].toFixed(1)}" cy="${ys[index].toFixed(1)}" r="2.6"></circle>`
      )
      .join("");
    return `
      <div class="trend-chart">
        <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="体重趋势">
          <path class="trend-area" d="${area}"></path>
          <path class="trend-line" d="${line}"></path>
          ${dots}
        </svg>
        <div class="trend-caption">
          <span>${fmtCN(points[0].date)}</span>
          <span>${min.toFixed(1)} - ${max.toFixed(1)} kg</span>
          <span>${fmtCN(points[points.length - 1].date)}</span>
        </div>
      </div>`;
  }

  function renderBodyHistory() {
    const root = $("#bodyHistory");
    if (!root) return;
    const items = state.bodyRecords;
    $("#bodyCount").textContent = items.length ? `${items.length} 条` : "";
    if (!items.length) {
      root.innerHTML = '<div class="empty-state">还没有身体数据，记录体重或导入手环数据吧。</div>';
      return;
    }
    root.innerHTML = items
      .map((item) => {
        const parts = [];
        if (item.weight_kg) parts.push(`体重 ${item.weight_kg} kg`);
        if (item.body_fat_pct) parts.push(`体脂 ${item.body_fat_pct}%`);
        if (item.muscle_kg) parts.push(`肌肉 ${item.muscle_kg} kg`);
        if (item.waist_cm) parts.push(`腰围 ${item.waist_cm} cm`);
        if (item.sleep_hours) parts.push(`睡眠 ${item.sleep_hours} h`);
        if (item.resting_hr) parts.push(`静息心率 ${item.resting_hr}`);
        if (item.steps) parts.push(`${item.steps} 步`);
        const source = item.source === "xiaomi" ? "手环" : "手动";
        return `
          <div class="list-item" data-id="${item.id}">
            <div class="icon-badge ${item.source === "xiaomi" ? "icon-badge--mint" : ""}">${esc(item.record_date.slice(5))}</div>
            <div class="item-main">
              <div class="item-title">${parts[0] || "身体数据"}<span class="tag">${source}</span></div>
              <div class="item-sub">${esc(item.record_date)}${parts.length ? ` · ${parts.join(" · ")}` : ""}${item.notes ? ` · ${esc(item.notes)}` : ""}</div>
            </div>
            <div class="item-actions">
              <button type="button" class="danger-link" data-action="delete">删除</button>
            </div>
          </div>`;
      })
      .join("");
  }

  async function submitBodyRecord(event) {
    event.preventDefault();
    const numberOrNull = (selector) => {
      const raw = $(selector).value;
      if (raw === "") return null;
      const value = Number(raw);
      return Number.isFinite(value) ? value : null;
    };
    const payload = {
      record_date: $("#bodyDate").value || todayISO(),
      weight_kg: numberOrNull("#bodyWeight"),
      body_fat_pct: numberOrNull("#bodyFat"),
      waist_cm: numberOrNull("#bodyWaist"),
      sleep_hours: numberOrNull("#bodySleep"),
      resting_hr: numberOrNull("#bodyRestingHr"),
      steps: numberOrNull("#bodySteps"),
      notes: $("#bodyNotes").value.trim(),
      source: "manual",
    };
    const measurements = [
      payload.weight_kg,
      payload.body_fat_pct,
      payload.waist_cm,
      payload.sleep_hours,
      payload.resting_hr,
      payload.steps,
    ];
    if (measurements.every((value) => value === null)) {
      toast("请至少填写一项身体数据");
      return;
    }
    try {
      await request("/api/body/records", { method: "POST", json: payload });
      toast("身体数据已记录");
      ["#bodyWeight", "#bodyFat", "#bodyWaist", "#bodySleep", "#bodyRestingHr", "#bodySteps", "#bodyNotes"].forEach(
        (selector) => {
          $(selector).value = "";
        }
      );
      $("#bodyDate").value = todayISO();
      await Promise.all([loadBodyData(), loadProfile(true)]);
    } catch (error) {
      toast(error.message);
    }
  }

  async function deleteBodyRecord(id) {
    if (!window.confirm("确定删除这条身体数据吗？")) return;
    try {
      await request(`/api/body/records/${id}`, { method: "DELETE" });
      toast("已删除");
      await Promise.all([loadBodyData(), loadProfile(true)]);
    } catch (error) {
      toast(error.message);
    }
  }

  async function deleteExerciseLog(id) {
    if (!window.confirm("确定删除这条运动记录吗？")) return;
    try {
      await request(`/api/exercise/logs/${id}`, { method: "DELETE" });
      toast("已删除");
      await Promise.all([loadExerciseLogs(), loadExerciseSummary()]);
    } catch (error) {
      toast(error.message);
    }
  }

  /* ---------------- 小米运动健康直连 ---------------- */

  function bindXiaomi() {
    $("#xiaomiLoginForm").addEventListener("submit", submitXiaomiLogin);
    $("#xiaomiVerifyBtn").addEventListener("click", submitXiaomiCode);
    $("#xiaomiChallengeCancel").addEventListener("click", cancelXiaomiChallenge);
    $("#xiaomiSync").addEventListener("click", () => syncXiaomi(false));
    $("#xiaomiLogout").addEventListener("click", logoutXiaomi);
  }

  async function loadXiaomiStatus() {
    try {
      state.xiaomiStatus = await request("/api/xiaomi/status");
      renderXiaomiStatus();
    } catch (error) {
      /* 忽略状态读取失败 */
    }
  }

  function renderXiaomiStatus() {
    const data = state.xiaomiStatus || { connected: false };
    const badge = $("#xiaomiStatusBadge");
    if (badge) badge.textContent = data.connected ? "已连接" : "未连接";
    $("#xiaomiConnected").classList.toggle("hidden", !data.connected);
    $("#xiaomiLoginForm").classList.toggle(
      "hidden",
      data.connected || Boolean(state.xiaomiAttemptId)
    );
    if (data.connected) {
      const chips = [
        `<span class="chip">${esc(data.username || "小米账号")}</span>`,
        `<span class="chip chip--mint">${data.region === "abroad" ? "海外区" : "中国大陆"}</span>`,
      ];
      if (data.last_sync) {
        chips.push(`<span class="chip chip--gold">上次同步 ${esc(data.last_sync)}</span>`);
      }
      const result = data.last_result || {};
      if (result.sport_records || result.steps_days || result.weight_records || result.sleep_days) {
        chips.push(
          `<span class="chip">运动 ${result.sport_records || 0} · 步数 ${result.steps_days || 0} 天 · 体重 ${result.weight_records || 0} 条 · 睡眠 ${result.sleep_days || 0} 天</span>`
        );
      }
      $("#xiaomiAccountChips").innerHTML = chips.join("");
    }
  }

  function showXiaomiChallenge(kind, data) {
    state.xiaomiAttemptId = data.attempt_id;
    state.xiaomiChallengeKind = kind;
    $("#xiaomiChallenge").classList.remove("hidden");
    $("#xiaomiLoginForm").classList.add("hidden");
    $("#xiaomiConnected").classList.add("hidden");
    $("#xiaomiCode").value = "";
    const image = $("#xiaomiCaptchaImage");
    if (kind === "captcha" && data.captcha_image) {
      image.src = data.captcha_image;
      image.classList.remove("hidden");
    } else {
      image.src = "";
      image.classList.add("hidden");
    }
    $("#xiaomiChallengeText").textContent =
      data.message ||
      (kind === "2fa"
        ? "请输入小米发送的二次验证码。"
        : "请输入图片验证码。");
    $("#xiaomiCode").focus();
  }

  function cancelXiaomiChallenge() {
    state.xiaomiAttemptId = null;
    state.xiaomiChallengeKind = null;
    $("#xiaomiChallenge").classList.add("hidden");
    $("#xiaomiCaptchaImage").classList.add("hidden");
    $("#xiaomiCode").value = "";
    renderXiaomiStatus();
  }

  function handleXiaomiResponse(data) {
    if (data.connected) {
      state.xiaomiStatus = data;
      state.xiaomiAttemptId = null;
      state.xiaomiChallengeKind = null;
      $("#xiaomiChallenge").classList.add("hidden");
      renderXiaomiStatus();
      toast("小米运动健康已连接");
      syncXiaomi(true);
      return;
    }
    if (data.status === "need_captcha") {
      showXiaomiChallenge("captcha", data);
      toast("请输入图片验证码");
      return;
    }
    if (data.status === "need_2fa") {
      showXiaomiChallenge("2fa", data);
      toast(data.message || "请输入二次验证码");
      return;
    }
    toast("连接状态已更新");
  }

  async function submitXiaomiLogin(event) {
    event.preventDefault();
    const payload = {
      username: $("#xiaomiUser").value.trim(),
      password: $("#xiaomiPassword").value,
      region: $("#xiaomiRegion").value,
    };
    if (!payload.username || !payload.password) {
      toast("请输入小米账号和密码");
      return;
    }
    const button = $("#xiaomiLoginBtn");
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "正在连接…";
    showLoading("正在登录小米账号…");
    try {
      const data = await request("/api/xiaomi/login", {
        method: "POST",
        json: payload,
      });
      handleXiaomiResponse(data);
    } catch (error) {
      toast(error.message);
      const result = $("#xiaomiResult");
      if (result) {
        result.innerHTML = `<div class="tip-box"><b>登录失败</b><div>${esc(error.message)}</div></div>`;
      }
    } finally {
      hideLoading();
      button.disabled = false;
      button.textContent = original;
    }
  }

  async function submitXiaomiCode() {
    const code = $("#xiaomiCode").value.trim();
    if (!code) {
      toast("请输入验证码");
      return;
    }
    if (!state.xiaomiAttemptId) {
      toast("验证会话已过期，请重新登录");
      cancelXiaomiChallenge();
      return;
    }
    const payload = { attempt_id: state.xiaomiAttemptId };
    if (state.xiaomiChallengeKind === "2fa") {
      payload.twofa_code = code;
    } else {
      payload.captcha = code;
    }
    const button = $("#xiaomiVerifyBtn");
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "正在验证…";
    showLoading("正在验证…");
    try {
      const data = await request("/api/xiaomi/login", {
        method: "POST",
        json: payload,
      });
      handleXiaomiResponse(data);
    } catch (error) {
      toast(error.message);
      const text = $("#xiaomiChallengeText");
      if (text) text.textContent = `验证未通过：${error.message}`;
      if (String(error.message).includes("会话已过期")) {
        cancelXiaomiChallenge();
      }
    } finally {
      hideLoading();
      button.disabled = false;
      button.textContent = original;
    }
  }

  async function syncXiaomi(auto) {
    if (!state.xiaomiStatus?.connected) {
      toast("请先连接小米运动健康账号");
      return;
    }
    const days = auto ? 7 : Number($("#xiaomiSyncDays").value) || 7;
    const button = $("#xiaomiSync");
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "同步中…";
    showLoading("正在从小米云端同步数据…");
    try {
      const data = await request(`/api/xiaomi/sync?days=${days}`, {
        method: "POST",
      });
      const lines = [
        `运动记录 ${data.sport_records || 0} 条`,
        `步数 ${data.steps_days || 0} 天`,
        `体重/身体数据 ${data.weight_records || 0} 条`,
        `睡眠 ${data.sleep_days || 0} 天`,
      ];
      const errors = Array.isArray(data.errors) ? data.errors : [];
      $("#xiaomiResult").innerHTML = `
        <div class="tip-box">
          <b>${auto ? "已连接并完成首次同步" : "同步完成"}</b>
          ${lines.map((line) => `<div>${esc(line)}</div>`).join("")}
          ${errors.length ? `<div>部分数据未同步：${esc(errors.join("；"))}</div>` : ""}
        </div>`;
      toast("小米数据同步完成");
      await Promise.all([
        loadXiaomiStatus(),
        loadExerciseLogs(),
        loadExerciseSummary(),
        loadBodyData(),
        loadProfile(true),
      ]);
    } catch (error) {
      toast(error.message);
    } finally {
      hideLoading();
      button.disabled = false;
      button.textContent = original;
    }
  }

  async function logoutXiaomi() {
    if (!window.confirm("确定断开小米运动健康连接吗？已同步的数据会保留。")) return;
    try {
      await request("/api/xiaomi/logout", { method: "POST" });
      state.xiaomiStatus = { connected: false };
      state.xiaomiAttemptId = null;
      state.xiaomiChallengeKind = null;
      $("#xiaomiChallenge").classList.add("hidden");
      $("#xiaomiResult").innerHTML = "";
      renderXiaomiStatus();
      toast("已断开连接");
    } catch (error) {
      toast(error.message);
    }
  }

  /* ---------------- AI 对话 ---------------- */

  function bindChat() {
    $("#chatForm").addEventListener("submit", submitChat);
    $("#chatClear").addEventListener("click", clearChat);
    $("#chatInput").addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        $("#chatForm").requestSubmit();
      }
    });
  }

  async function loadChatHistory() {
    try {
      const data = await request("/api/chat/messages?limit=100");
      state.chatMessages = data.items || [];
      renderChat();
    } catch (error) {
      toast(error.message);
    }
  }

  function renderChat() {
    const list = $("#chatList");
    if (!list) return;
    const items = state.chatMessages || [];
    if (!items.length) {
      list.innerHTML = `
        <div class="chat-message chat-message--assistant">
          你好，我是 ShyHealthHelper 的营养与运动助手。你可以问我：今天晚餐吃什么？蛋白质够不够？今天还可以做哪些运动？
        </div>`;
      return;
    }
    list.innerHTML = items
      .map(
        (item) =>
          `<div class="chat-message chat-message--${item.role === "user" ? "user" : "assistant"}">${esc(item.content)}</div>`
      )
      .join("");
    scrollChat();
  }

  function appendChatBubble(role, content) {
    const list = $("#chatList");
    if (!list) return;
    if (!state.chatMessages.length) list.innerHTML = "";
    const bubble = document.createElement("div");
    bubble.className = `chat-message chat-message--${role === "user" ? "user" : "assistant"}`;
    bubble.textContent = content;
    list.appendChild(bubble);
    scrollChat();
  }

  function scrollChat() {
    const list = $("#chatList");
    if (list) list.scrollTop = list.scrollHeight;
  }

  async function submitChat(event) {
    event.preventDefault();
    const input = $("#chatInput");
    const message = input.value.trim();
    if (!message) return;
    input.value = "";
    appendChatBubble("user", message);
    appendChatBubble("assistant", "正在思考…");
    const button = $("#chatSend");
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "思考中…";
    try {
      await request("/api/chat", {
        method: "POST",
        json: { message },
      });
      await loadChatHistory();
    } catch (error) {
      toast(error.message);
      await loadChatHistory();
    } finally {
      button.disabled = false;
      button.textContent = original;
      input.focus();
    }
  }

  async function clearChat() {
    if (!window.confirm("确定清空全部对话吗？")) return;
    try {
      await request("/api/chat/messages", { method: "DELETE" });
      state.chatMessages = [];
      renderChat();
      toast("对话已清空");
    } catch (error) {
      toast(error.message);
    }
  }

  /* ---------------- AI 设置 ---------------- */

  function bindAISettings() {
    $("#aiSettingsForm").addEventListener("submit", saveAISettings);
    $("#aiTest").addEventListener("click", testAIConnection);
    $("#aiClear").addEventListener("click", clearAISettings);
  }

  async function loadAISettings() {
    try {
      const data = await request("/api/ai/settings");
      renderAISettings(data);
      if (state.health) {
        state.health.ai_mode = data.ai_mode;
        state.health.mock_mode = data.mock_mode;
        renderMode();
      }
    } catch (error) {
      toast(error.message);
    }
  }

  function renderAISettings(data) {
    const status = $("#aiStatus");
    if (!status || !data) return;
    status.textContent = data.configured ? "已配置" : "未配置";
    status.className = `hint ${data.configured ? "ai-status-ok" : "ai-status-off"}`;
    const keyInput = $("#aiKey");
    keyInput.value = "";
    keyInput.placeholder = data.configured
      ? `已保存：${data.api_key_masked}（留空不修改）`
      : "sk-...";
    $("#aiBaseUrl").value = data.base_url || "";
    $("#aiModel").value = data.model || "";
    $("#aiVisionModel").value = data.vision_model || "";
    const result = $("#aiSettingsResult");
    result.innerHTML = data.configured
      ? `<div class="tip-box"><b>AI 已配置</b><div>文本模型 ${esc(data.model)} · 视觉模型 ${esc(data.vision_model)}</div></div>`
      : `<div class="tip-box"><b>当前为本地模式</b><div>填写 DeepSeek API Key 后启用真实照片识别和 AI 对话。</div></div>`;
  }

  async function refreshHealth() {
    try {
      state.health = await request("/api/health");
      renderMode();
    } catch (error) {
      /* 忽略 */
    }
  }

  async function saveAISettings(event) {
    event.preventDefault();
    const key = $("#aiKey").value.trim();
    const payload = {
      base_url: $("#aiBaseUrl").value.trim() || null,
      model: $("#aiModel").value.trim() || null,
      vision_model: $("#aiVisionModel").value.trim() || null,
    };
    if (key) payload.api_key = key;
    const button = $("#aiSave");
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "保存中…";
    showLoading("正在保存 AI 设置…");
    try {
      const data = await request("/api/ai/settings", {
        method: "PUT",
        json: payload,
      });
      renderAISettings(data);
      await refreshHealth();
      toast("AI 设置已保存");
    } catch (error) {
      toast(error.message);
    } finally {
      hideLoading();
      button.disabled = false;
      button.textContent = original;
    }
  }

  async function testAIConnection() {
    const button = $("#aiTest");
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "测试中…";
    showLoading("正在测试 DeepSeek 连接…");
    try {
      const data = await request("/api/ai/test", { method: "POST" });
      renderAISettings(data);
      $("#aiSettingsResult").innerHTML = `
        <div class="tip-box">
          <b>${data.ok ? "连接成功" : "连接失败"}</b>
          <div>${esc(data.message || "")}</div>
        </div>`;
      await refreshHealth();
      toast(data.ok ? "DeepSeek 连接正常" : "连接失败，请检查 Key 和网络");
    } catch (error) {
      toast(error.message);
    } finally {
      hideLoading();
      button.disabled = false;
      button.textContent = original;
    }
  }

  async function clearAISettings() {
    if (!window.confirm("确定清除已保存的 API Key 吗？")) return;
    try {
      const data = await request("/api/ai/settings", { method: "DELETE" });
      renderAISettings(data);
      await refreshHealth();
      toast("已清除 API Key");
    } catch (error) {
      toast(error.message);
    }
  }

  /* ---------------- 记账 ---------------- */

  function bindFinance() {
    $("#financeMonth").addEventListener("change", () => {
      state.financeMonth = $("#financeMonth").value || currentMonth();
      loadFinance();
    });
    $("#financeForm").addEventListener("submit", submitFinance);
    $("#financeList").addEventListener("click", (event) => {
      const action = event.target.closest("[data-action='delete']");
      if (!action) return;
      const id = Number(action.closest(".list-item").dataset.id);
      deleteFinance(id);
    });
    $("#copyApiBtn").addEventListener("click", copyApiBase);
  }

  function renderFinanceCategories() {
    const select = $("#financeCategory");
    if (!select) return;
    const categories = state.financeType === "income" ? INCOME_CATEGORIES : EXPENSE_CATEGORIES;
    const previous = select.value;
    select.innerHTML = categories.map((item) => `<option value="${item}">${item}</option>`).join("");
    if (categories.includes(previous)) select.value = previous;
  }

  async function loadFinance() {
    const month = $("#financeMonth").value || state.financeMonth || currentMonth();
    state.financeMonth = month;
    try {
      const [summary, records] = await Promise.all([
        request(`/api/finance/summary?month=${encodeURIComponent(month)}`),
        request(`/api/finance/records?month=${encodeURIComponent(month)}&limit=200`),
      ]);
      renderFinanceSummary(summary);
      renderFinanceRecords(records.items || []);
    } catch (error) {
      toast(error.message);
    }
  }

  function renderFinanceSummary(summary) {
    const expense = $("#sumExpense");
    const income = $("#sumIncome");
    const balance = $("#sumBalance");
    expense.textContent = money(summary.expense);
    expense.className = "expense";
    income.textContent = money(summary.income);
    income.className = "income";
    balance.textContent = money(summary.balance);
    balance.className = summary.balance < 0 ? "expense" : "income";

    const monthText = summary.month ? summary.month.replace("-", "年") + "月" : "";
    $("#financeMonth").title = monthText;

    const categories = (summary.by_category || [])
      .filter((item) => item.type === "expense")
      .slice(0, 4);
    $("#expenseBreakdown").innerHTML = categories.length
      ? categories
          .map(
            (item) => `
            <div class="breakdown-row">
              <span>${esc(item.category)}</span>
              <div class="breakdown-bar"><span style="width:${clampPercent((item.ratio || 0) * 100)}%"></span></div>
              <b>${money(item.amount)}</b>
            </div>`
          )
          .join("")
      : "";
  }

  function renderFinanceRecords(items) {
    const root = $("#financeList");
    $("#financeCount").textContent = items.length ? `${items.length} 笔` : "";
    if (!items.length) {
      root.innerHTML = '<div class="empty-state">本月还没有记录，添加第一笔收支吧。</div>';
      return;
    }
    root.innerHTML = items
      .map((item) => {
        const isIncome = item.type === "income";
        const sourceLabel = item.source === "wechat" ? "微信小程序" : "";
        return `
          <div class="list-item" data-id="${item.id}">
            <div class="icon-badge ${isIncome ? "icon-badge--mint" : ""}">${esc((item.category || "其")[0])}</div>
            <div class="item-main">
              <div class="item-title">${esc(item.category)}${item.note ? ` · ${esc(item.note)}` : ""}</div>
              <div class="item-sub">${esc(item.record_date)}${sourceLabel ? ` · ${sourceLabel}` : ""}</div>
            </div>
            <div class="item-actions">
              <span class="item-amount ${isIncome ? "income" : "expense"}">${isIncome ? "+" : "-"}${money(item.amount).replace("-", "")}</span>
              <button type="button" class="danger-link" data-action="delete">删除</button>
            </div>
          </div>`;
      })
      .join("");
  }

  async function submitFinance(event) {
    event.preventDefault();
    const amount = Number($("#financeAmount").value);
    if (!Number.isFinite(amount) || amount <= 0) {
      toast("请输入有效金额");
      return;
    }
    const payload = {
      record_date: $("#financeDate").value || todayISO(),
      type: state.financeType,
      amount,
      category: $("#financeCategory").value,
      note: $("#financeNote").value.trim(),
      source: "web",
    };
    try {
      await request("/api/finance/records", { method: "POST", json: payload });
      toast("已记一笔");
      $("#financeAmount").value = "";
      $("#financeNote").value = "";
      await loadFinance();
    } catch (error) {
      toast(error.message);
    }
  }

  async function deleteFinance(id) {
    if (!window.confirm("确定删除这条账单吗？")) return;
    try {
      await request(`/api/finance/records/${id}`, { method: "DELETE" });
      toast("已删除");
      await loadFinance();
    } catch (error) {
      toast(error.message);
    }
  }

  async function copyApiBase() {
    const text = location.origin;
    try {
      await navigator.clipboard.writeText(text);
      toast("后端地址已复制");
    } catch (error) {
      toast(`请手动复制：${text}`);
    }
  }

  function updateApiBase() {
    const element = $("#apiBaseText");
    if (element) element.textContent = location.origin;
  }

  /* ---------------- Service Worker ---------------- */

  function registerServiceWorker() {
    updateApiBase();
    const isEmbedded = new URLSearchParams(location.search).has("embedded");
    if (isEmbedded) {
      // 内置 APK 的页面由本地 FastAPI 提供，不需要 Service Worker。
      // 同时注销旧版本可能遗留的注册并清理缓存，避免更新后仍显示旧页面。
      if ("serviceWorker" in navigator) {
        navigator.serviceWorker
          .getRegistrations()
          .then((registrations) => {
            registrations.forEach((registration) => registration.unregister());
          })
          .catch(() => {});
      }
      if (window.caches) {
        caches
          .keys()
          .then((keys) => Promise.all(keys.map((key) => caches.delete(key))))
          .catch(() => {});
      }
      return;
    }
    if (!("serviceWorker" in navigator) || !location.protocol.startsWith("http")) return;
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js").catch(() => {
        /* 忽略注册失败，例如浏览器隐私模式 */
      });
    });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
