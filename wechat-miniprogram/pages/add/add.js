const { request } = require("../../utils/api");
const { today } = require("../../utils/format");

const EXPENSE_CATEGORIES = ["餐饮", "交通", "购物", "居住", "医疗", "娱乐", "学习", "人情", "其他"];
const INCOME_CATEGORIES = ["工资", "奖金", "理财", "兼职", "红包", "其他"];

Page({
  data: {
    type: "expense",
    categories: EXPENSE_CATEGORIES,
    categoryIndex: 0,
    amount: "",
    date: "",
    note: "",
    saving: false,
  },

  onLoad() {
    this.setData({ date: today() });
  },

  onType(event) {
    const type = event.currentTarget.dataset.type;
    const categories = type === "income" ? INCOME_CATEGORIES : EXPENSE_CATEGORIES;
    this.setData({ type, categories, categoryIndex: 0 });
  },

  onAmount(event) {
    this.setData({ amount: event.detail.value });
  },

  onCategory(event) {
    this.setData({ categoryIndex: Number(event.detail.value) });
  },

  onDate(event) {
    this.setData({ date: event.detail.value });
  },

  onNote(event) {
    this.setData({ note: event.detail.value });
  },

  onSave() {
    const amount = Number(this.data.amount);
    if (!Number.isFinite(amount) || amount <= 0) {
      wx.showToast({ title: "请输入有效金额", icon: "none" });
      return;
    }
    if (this.data.saving) return;

    this.setData({ saving: true });
    request("/api/finance/records", {
      method: "POST",
      data: {
        record_date: this.data.date,
        type: this.data.type,
        amount,
        category: this.data.categories[this.data.categoryIndex],
        note: this.data.note.trim(),
        source: "wechat",
      },
    })
      .then(() => {
        this.setData({ saving: false });
        wx.showToast({ title: "已保存", icon: "success" });
        setTimeout(() => wx.navigateBack(), 600);
      })
      .catch((error) => {
        this.setData({ saving: false });
        wx.showToast({ title: error.message.slice(0, 18), icon: "none" });
      });
  },
});
