function getBaseUrl() {
  const app = getApp();
  const base = (app && app.globalData && app.globalData.apiBase) || "http://127.0.0.1:8000";
  return base.replace(/\/+$/, "");
}

function request(path, options = {}) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: getBaseUrl() + path,
      method: options.method || "GET",
      data: options.data,
      timeout: 20000,
      header: { "content-type": "application/json" },
      success(response) {
        if (response.statusCode >= 200 && response.statusCode < 300) {
          resolve(response.data);
          return;
        }
        const detail = response.data && response.data.detail;
        reject(new Error(typeof detail === "string" ? detail : "请求失败"));
      },
      fail() {
        reject(new Error("无法连接后端，请检查 apiBase 与网络"));
      },
    });
  });
}

module.exports = { request, getBaseUrl };
