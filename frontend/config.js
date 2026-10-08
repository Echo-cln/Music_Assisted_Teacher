// 默认同源调用 EdgeOne Python 云函数（/api）。只有后端独立部署时，才将 apiBaseUrl 改为后端的 HTTPS /api 地址。
window.__APP_CONFIG__ = window.__APP_CONFIG__ || { apiBaseUrl: "/api" };
