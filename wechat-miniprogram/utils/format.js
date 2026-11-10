function pad(value) {
  return String(value).padStart(2, "0");
}

function today() {
  const now = new Date();
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

function currentMonth() {
  const now = new Date();
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}`;
}

function formatMoney(value) {
  const number = Number(value) || 0;
  const sign = number < 0 ? "-" : "";
  return `${sign}¥${Math.abs(number).toFixed(2)}`;
}

function monthLabel(month) {
  if (!month) return "";
  const parts = month.split("-");
  return `${parts[0]}年${Number(parts[1])}月`;
}

module.exports = { today, currentMonth, formatMoney, monthLabel };
