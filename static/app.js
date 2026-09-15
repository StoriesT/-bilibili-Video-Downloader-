const $ = (id) => document.getElementById(id);

let pollTimer = null;
let downloadTimer = null;
let downloadRunning = false;

// ---------- 登录 ----------
async function refreshLoginStatus() {
  try {
    const r = await fetch('/api/login/status');
    const d = await r.json();
    if (d.logged_in) {
      $('login-view').classList.add('hidden');
      $('loggedin-view').classList.remove('hidden');
      $('uname').textContent = d.uname || 'B站用户';
      $('login-badge').textContent = '已登录';
      $('login-badge').classList.add('on');
    } else {
      $('login-view').classList.remove('hidden');
      $('loggedin-view').classList.add('hidden');
      $('login-badge').textContent = '未登录';
      $('login-badge').classList.remove('on');
    }
  } catch (e) {
    /* 忽略网络错误 */
  }
}

function stopPoll() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

function renderQr(text) {
  try {
    const qr = qrcode(0, 'M');
    qr.addData(text);
    qr.make();
    $('qrcode').src = qr.createDataURL(6, 2);
  } catch (e) {
    $('login-msg').textContent = '二维码渲染失败';
  }
}

async function startLogin() {
  stopPoll();
  $('qr-overlay').classList.add('hidden');
  $('login-msg').textContent = '正在生成二维码…';
  try {
    const r = await fetch('/api/login/start', { method: 'POST' });
    const d = await r.json();
    if (!d.ok) {
      $('login-msg').textContent = '生成失败：' + (d.error || '');
      return;
    }
    renderQr(d.qrcode_url);
    $('login-msg').textContent = '请用 B 站 App 扫码';
    startPoll(d.qrcode_key);
  } catch (e) {
    $('login-msg').textContent = '生成失败，请重试';
  }
}

function startPoll(key) {
  stopPoll();
  pollTimer = setInterval(async () => {
    try {
      const r = await fetch('/api/login/poll?key=' + encodeURIComponent(key) + '&t=' + Date.now());
      const d = await r.json();
      if (!d.ok) {
        $('login-msg').textContent = '轮询失败：' + (d.error || '');
        return;
      }
      if (d.state === 'scanned') {
        $('login-msg').textContent = '已扫码，请在手机上确认';
      } else if (d.state === 'confirmed') {
        stopPoll();
        $('login-msg').textContent = '登录成功！';
        await refreshLoginStatus();
      } else if (d.state === 'expired') {
        stopPoll();
        $('login-msg').textContent = '二维码已失效，请点击刷新';
        $('qr-overlay').classList.remove('hidden');
      }
      // waiting: 保持“请用 B 站 App 扫码”文案
    } catch (e) {
      $('login-msg').textContent = '轮询出错：' + e;
    }
  }, 2000);
}

// ---------- 下载 ----------
async function startDownload() {
  if (downloadRunning) return;
  const urls = $('urls').value.split('\n').map(s => s.trim()).filter(Boolean);
  if (!urls.length) { alert('请先粘贴视频链接'); return; }

  try {
    const r = await fetch('/api/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ urls })
    });
    const d = await r.json();
    if (!d.ok) { alert(d.error || '启动失败'); return; }
  } catch (e) { alert('启动失败：' + e); return; }

  downloadRunning = true;
  $('btn-download').disabled = true;
  $('btn-cancel').classList.remove('hidden');
  $('progress-box').classList.remove('hidden');
  $('progress-bar').style.width = '0';
  $('log').textContent = '';
  startDownloadPoll();
}

function stopDownloadPoll() {
  if (downloadTimer) { clearInterval(downloadTimer); downloadTimer = null; }
}

function startDownloadPoll() {
  stopDownloadPoll();
  downloadTimer = setInterval(async () => {
    try {
      const r = await fetch('/api/download/status');
      const s = await r.json();
      renderStatus(s);
      if (['done', 'error', 'cancelled'].indexOf(s.state) >= 0) {
        stopDownloadPoll();
        downloadRunning = false;
        $('btn-download').disabled = false;
        $('btn-cancel').classList.add('hidden');
      }
    } catch (e) { /* 忽略 */ }
  }, 800);
}

function renderStatus(s) {
  let pct = (typeof s.percent === 'number') ? s.percent : 0;
  pct = Math.min(100, Math.max(0, pct));
  $('progress-bar').style.width = pct + '%';

  const idx = (s.current_index || 0) + 1;
  let label = '';
  if (s.state === 'running') {
    label = '正在下载 ' + idx + '/' + s.total;
    if (pct > 0) label += ' · ' + pct.toFixed(1) + '%';
  } else if (s.state === 'done') {
    label = '✅ ' + (s.message || '全部完成');
  } else if (s.state === 'error') {
    label = '❌ ' + (s.message || '下载失败');
  } else if (s.state === 'cancelled') {
    label = '已取消';
  } else {
    label = s.message || '';
  }
  $('progress-text').textContent = label;
  $('progress-speed').textContent = s.speed || '';
  $('progress-eta').textContent = s.eta ? ('剩余 ' + s.eta) : '';

  if (s.log && s.log.length) {
    $('log').textContent = s.log.join('\n');
    $('log').scrollTop = $('log').scrollHeight;
  }
}

async function cancelDownload() {
  try { await fetch('/api/download/cancel', { method: 'POST' }); } catch (e) { /* 忽略 */ }
}

async function openFolder() {
  try { await fetch('/api/open-folder', { method: 'POST' }); } catch (e) { /* 忽略 */ }
}

// ---------- 事件绑定 ----------
$('btn-login').addEventListener('click', startLogin);
$('btn-relogin').addEventListener('click', () => {
  $('login-view').classList.remove('hidden');
  $('loggedin-view').classList.add('hidden');
  startLogin();
});
$('btn-download').addEventListener('click', startDownload);
$('btn-cancel').addEventListener('click', cancelDownload);
$('btn-open-folder').addEventListener('click', openFolder);

// ---------- 初始化 ----------
(async () => {
  await refreshLoginStatus();
  if (!$('login-badge').classList.contains('on')) {
    startLogin(); // 未登录时自动生成二维码
  }
})();
