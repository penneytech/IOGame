// Tiny shared helpers used by multiple pages. Loaded as a regular script.
window.IOG = window.IOG || {};

IOG.wsUrl = function () {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  return proto + '//' + location.host + '/ws';
};

IOG.saveSession = function (data) {
  try { sessionStorage.setItem('iog.session', JSON.stringify(data)); }
  catch (e) { /* ignore */ }
};

IOG.loadSession = function () {
  try {
    const s = sessionStorage.getItem('iog.session');
    return s ? JSON.parse(s) : null;
  } catch (e) { return null; }
};

IOG.clearSession = function () {
  try { sessionStorage.removeItem('iog.session'); } catch (e) {}
};
