const { request } = require("../../utils/api");
const { currentMonth, formatMoney, monthLabel } = require("../../utils/format");

Page({
  data: {
    month: "",
    monthText: "",
    incomeText: "¥0.00",
    expenseText: "¥0.00",
    balanceText: "¥0.00",
    balanceClass: "",
    categories: [],
    records: [],
    count: 0,
    loading: false,
  },

  onLoad() {
    const month = currentMonth();
    this.setData({ month, monthText: monthLabel(month) });
  },

  onShow() {
    this.loadData();
  },

  onPullDownRefresh() {
    this.loadData().then(() => wx.stopPullDownRefresh());
  },

  onMonthChange(event) {
    const month = event.detail.value;
    this.setData({ month, monthText: monthLabel(month) });
    this.loadData();
  },

  async loadData() {
    const month = this.data.month;
    if (!month) return;
    this.setData({ loading: true });
    try {
      const [summary, records] = await Promise.all([
        request(`/api/finance/summary?month=${month}`),
        request(`/api/finance/records?month=${month}&limit=200`),
      ]);

      const categories = (summary.by_category || [])
        .filter((item) => item.type === "expense")
        .slice(0, 4)
        .map((item) => ({
          category: item.category,
          percent: Math.round((item.ratio || 0) * 100),
          amountText: formatMoney(item.amount),
        }));

      const items = (records.items || []).map((item) => ({
        id: item.id,
        category: item.category,
        note: item.note,
        record_date: item.record_date,
        type: item.type,
        badge: (item.category || "其").slice(0, 1),
        amountText:
          (item.type === "income" ? "+" : "-") +
          formatMoney(item.amount).replace("-", ""),
        sourceText: item.source === "wechat" ? " · 微信小程序" : "",
      }));

      this.setData({
        incomeText: formatMoney(summary.income),
        expenseText: formatMoney(summary.expense),
        balanceText: formatMoney(summary.balance),
        balanceClass: summary.balance < 0 ? "negative" : "positive",
        categories,
        records: items,
        count: items.length,
      });
    } catch (error) {
      wx.showToast({ title: error.message.slice(0, 18), icon: "none" });
    } finally {
      this.setData({ loading: false });
    }
  },

  onAdd() {
    wx.navigateTo({ url: "/pages/add/add" });
  },

  onDelete(event) {
    const id = event.currentTarget.dataset.id;
    wx.showModal({
      title: "删除账单",
      content: "确定删除这条记录吗？",
      confirmColor: "#c94f6d",
      success: (result) => {
        if (!result.confirm) return;
        request(`/api/finance/records/${id}`, { method: "DELETE" })
          .then(() => {
            wx.showToast({ title: "已删除", icon: "success" });
            this.loadData();
          })
          .catch((error) => {
            wx.showToast({ title: error.message.slice(0, 18), icon: "none" });
          });
      },
    });
  },
});
