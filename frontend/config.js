// Frontend -> Backend API Configuration
// Automatically connects to the live Railway Backend API in production (Vercel)
window.API_BASE = (window.location.hostname === "127.0.0.1" || window.location.hostname === "localhost") && window.location.port === "8765"
  ? ""
  : "https://gold-signal-api-production.up.railway.app";
