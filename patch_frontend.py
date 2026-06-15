import re

with open('index.html', 'r', encoding='utf-8') as f:
    html = f.read()

css_inject = """
/* ─── ADMIN & SUB STYLES ────── */
.admin-tab-bar {
  display: flex; gap: 8px; overflow-x: auto; padding: 14px 16px; border-bottom: 1px solid var(--border);
  scrollbar-width: none;
}
.admin-tab-bar::-webkit-scrollbar { display: none; }
.admin-tab {
  padding: 8px 14px; border-radius: var(--r-pill); font-size: 13px; font-weight: 600; color: var(--muted);
  background: var(--surface2); cursor: pointer; white-space: nowrap; transition: all .2s; border: 1px solid transparent;
}
.admin-tab.act { background: var(--accent-dim); color: var(--accent); border-color: rgba(91,143,255,.2); }
.admin-panel-content { display: none; padding: 14px 16px; }
.admin-panel-content.act { display: block; }
.stat-box {
  background: var(--surface2); border: 1px solid var(--border); border-radius: var(--r-md); padding: 16px;
  display: flex; flex-direction: column; gap: 6px; flex: 1; min-width: 45%;
}
.stat-val { font-size: 24px; font-weight: 800; color: var(--text); }
.stat-lbl { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; }
.user-row { background: var(--surface2); border: 1px solid var(--border); border-radius: var(--r-md); padding: 14px; margin-bottom: 10px; }
.user-row strong { display: block; font-size: 14px; margin-bottom: 4px; }
.user-row span { display: block; font-size: 12px; color: var(--muted); margin-bottom: 2px; }
.pay-box { background: var(--surface2); border: 1px solid var(--warn-dim); border-radius: var(--r-md); padding: 14px; margin-bottom: 10px; }
.sub-plan-card {
  background: var(--surface2); border: 2px solid var(--border-bright); border-radius: var(--r-lg); padding: 20px;
  text-align: center; cursor: pointer; transition: all .2s; margin-bottom: 14px;
}
.sub-plan-card.sel { border-color: var(--accent); background: var(--accent-dim); box-shadow: 0 4px 20px var(--accent-glow); }
.sub-price { font-size: 28px; font-weight: 800; color: var(--text); margin: 8px 0; }
"""

html = html.replace('/* ─── CONTENT ─────────────────── */', css_inject + '\n/* ─── CONTENT ─────────────────── */')

html_inject = """
<!-- SUB PAYWALL -->
<div class="screen" id="s-sub">
  <div class="hdr">
    <div class="hdr-title" style="text-align:center">Obuna muddati tugagan</div>
  </div>
  <div class="content" style="padding: 20px 16px">
    <div style="text-align:center; margin-bottom:24px">
      <div style="font-size:48px; margin-bottom:12px">🔒</div>
      <h2 style="font-size:18px; margin-bottom:8px">Botdan foydalanish uchun obuna sotib oling</h2>
      <p style="font-size:13px; color:var(--muted)">Sizning obuna muddatlaringiz tugagan yoki hali sotib olinmagan.</p>
    </div>
    
    <div class="sub-plan-card sel" onclick="selectMonths(1)" id="plan-1">
      <div style="font-size:14px; font-weight:600; color:var(--accent)">1 Oylik obuna</div>
      <div class="sub-price" id="subPriceDisplay">15,000 so'm</div>
    </div>
    
    <div class="sub-plan-card" onclick="selectMonths(3)" id="plan-3">
      <div style="font-size:14px; font-weight:600; color:var(--success)">3 Oylik obuna</div>
      <div class="sub-price" id="subPriceDisplay3">45,000 so'm</div>
    </div>

    <button class="btn btn-p" onclick="requestSub()" id="btn-req-sub">Obuna bo'lish <i class="fa-solid fa-arrow-right"></i></button>
  </div>
</div>

<!-- PAYMENT PROCESS -->
<div class="screen" id="s-pay">
  <div class="hdr">
    <div class="hdr-title" style="text-align:center">To'lov qilish</div>
  </div>
  <div class="content" style="padding: 20px 16px">
    <div style="background:var(--surface2); border:1px solid var(--border); border-radius:var(--r-lg); padding:20px; text-align:center; margin-bottom:20px">
      <div style="font-size:13px; color:var(--muted); margin-bottom:8px">To'lanishi kerak bo'lgan summa:</div>
      <div style="font-size:32px; font-weight:800; color:var(--success); letter-spacing:1px" id="pay-amount-display">0 so'm</div>
      <div style="font-size:12px; color:var(--warn); margin-top:8px; font-weight:600"><i class="fa-solid fa-triangle-exclamation"></i> Summani aniq kiritganingizga ishonch hosil qiling! Bot avtomatik tekshiradi.</div>
    </div>
    
    <div style="background:var(--surface2); border:1px solid var(--border); border-radius:var(--r-lg); padding:16px; margin-bottom:20px">
      <div style="font-size:13px; color:var(--muted); margin-bottom:12px">Quyidagi kartaga to'lov qiling:</div>
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px">
        <strong style="font-size:18px; letter-spacing:2px" id="pay-card-num">8600 0000 0000 0000</strong>
        <i class="fa-solid fa-copy" style="color:var(--accent); cursor:pointer" onclick="navigator.clipboard.writeText(document.getElementById('pay-card-num').textContent); toast('Karta nusxalandi')"></i>
      </div>
      <div style="font-size:13px; color:var(--text2)" id="pay-card-owner">Admin</div>
    </div>
    
    <button class="btn btn-p" onclick="toast('Bot to\\'lovni avtomatik tekshirmoqda. Iltimos kuting...','ok'); setTimeout(()=>go('s-home'), 3000)">
      <i class="fa-solid fa-check-circle"></i> To'lov qildim
    </button>
  </div>
</div>

<!-- ADMIN PANEL -->
<div class="screen" id="s-admin">
  <div class="hdr">
    <button class="hdr-back" onclick="go('s-home')"><i class="fa-solid fa-arrow-left"></i></button>
    <div class="hdr-title">Admin Panel</div>
  </div>
  <div class="admin-tab-bar">
    <div class="admin-tab act" onclick="switchAdminTab('stats')" id="tab-stats">📊 Statistika</div>
    <div class="admin-tab" onclick="switchAdminTab('users')" id="tab-users">👥 Foydalanuvchilar</div>
    <div class="admin-tab" onclick="switchAdminTab('payments')" id="tab-payments">✅ To'lovlar</div>
    <div class="admin-tab" onclick="switchAdminTab('settings')" id="tab-settings">⚙️ Sozlamalar</div>
  </div>
  <div class="content">
    <div class="admin-panel-content act" id="pnl-stats">
      <div style="display:flex; flex-wrap:wrap; gap:10px">
        <div class="stat-box"><span class="stat-lbl">Jami foydalanuvchilar</span><span class="stat-val" id="st-total">0</span></div>
        <div class="stat-box"><span class="stat-lbl">Aktiv obunalar</span><span class="stat-val" style="color:var(--success)" id="st-active">0</span></div>
        <div class="stat-box"><span class="stat-lbl">Muddati tugagan</span><span class="stat-val" style="color:var(--danger)" id="st-exp">0</span></div>
        <div class="stat-box"><span class="stat-lbl">Oylik daromad</span><span class="stat-val" style="color:var(--accent)" id="st-rev">0 UZS</span></div>
      </div>
    </div>
    <div class="admin-panel-content" id="pnl-users">
      <div id="admin-users-list"></div>
    </div>
    <div class="admin-panel-content" id="pnl-payments">
      <div id="admin-pay-list"></div>
    </div>
    <div class="admin-panel-content" id="pnl-settings">
      <div class="card" style="margin:0">
        <div style="padding:16px">
          <label style="font-size:12px; color:var(--muted); margin-bottom:6px; display:block">Yangi Parol</label>
          <input type="password" class="inp" id="adm-set-pass" placeholder="Parol...">
          <label style="font-size:12px; color:var(--muted); margin:12px 0 6px; display:block">Kanal ID (CardXabar)</label>
          <input type="text" class="inp" id="adm-set-channel" placeholder="-100...">
          <label style="font-size:12px; color:var(--muted); margin:12px 0 6px; display:block">Oylik obuna narxi</label>
          <input type="number" class="inp" id="adm-set-price" placeholder="15000">
          <button class="btn btn-p" style="margin-top:16px" onclick="saveAdminSettings()">Saqlash</button>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- ADMIN LOGIN MODAL -->
<div class="modal-bg" id="m-admin-login">
  <div class="modal">
    <div class="modal-handle"></div>
    <div class="modal-title">Admin Panelga kirish</div>
    <div class="modal-sub">Iltimos, parolni kiriting</div>
    <input type="password" class="inp" id="inp-admin-pass" placeholder="Parol...">
    <button class="btn btn-p" style="margin-top:16px" onclick="loginAdmin()">Kirish</button>
  </div>
</div>

"""

html = html.replace('<!-- MENU PANEL -->', html_inject + '\n<!-- MENU PANEL -->')

# Add Admin Panel button to Menu
menu_btn = """
      <div class="card-row" onclick="closeModal('m-menu'); openModal('m-admin-login')">
        <div style="width:34px;height:34px;border-radius:var(--r-sm);background:rgba(255,165,2,.15);display:flex;align-items:center;justify-content:center;color:var(--warn);font-size:13px;flex-shrink:0"><i class="fa-solid fa-lock"></i></div>
        <div style="flex:1"><strong style="font-size:14px">Admin Panel</strong></div>
        <span class="chev"><i class="fa-solid fa-chevron-right" style="font-size:9px"></i></span>
      </div>
"""
html = html.replace('<div class="card" style="margin:0 0 10px">', '<div class="card" style="margin:0 0 10px">' + menu_btn)

# Add JS Logics
js_inject = """
// ═══════════════════════════════
// SUB & ADMIN LOGIC
// ═══════════════════════════════
let subPrice = 15000;
let selMonths = 1;
let adminPass = '';

async function checkSubStatus(){
  if(UID === 'demo_user') return;
  try {
    const r = await fetch(`${API}/sub/status/${UID}`);
    const d = await r.json();
    subPrice = d.price || 15000;
    document.getElementById('subPriceDisplay').textContent = subPrice.toLocaleString('uz-UZ') + " so'm";
    document.getElementById('subPriceDisplay3').textContent = (subPrice * 3).toLocaleString('uz-UZ') + " so'm";
    if(!d.active) {
      go('s-sub');
    }
  } catch(e){}
}

function selectMonths(m) {
  selMonths = m;
  document.getElementById('plan-1').classList.remove('sel');
  document.getElementById('plan-3').classList.remove('sel');
  document.getElementById(`plan-${m}`).classList.add('sel');
}

async function requestSub(){
  const btn = document.getElementById('btn-req-sub');
  btn.disabled = true; btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Kuting...';
  try {
    const r = await fetch(`${API}/sub/request`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        user_id: String(UID), months: selMonths,
        phone: document.getElementById('home-conn')?.textContent || '',
        name: window.Telegram?.WebApp?.initDataUnsafe?.user?.first_name || '',
        username: window.Telegram?.WebApp?.initDataUnsafe?.user?.username || ''
      })
    });
    const d = await r.json();
    if(d.ok) {
      document.getElementById('pay-amount-display').textContent = d.amount.toLocaleString('uz-UZ') + " so'm";
      go('s-pay');
    } else {
      toast("Xatolik", "err");
    }
  } catch(e){ toast("Xatolik", "err"); }
  btn.disabled = false; btn.innerHTML = 'Obuna bo\\'lish <i class="fa-solid fa-arrow-right"></i>';
}

async function loginAdmin(){
  const p = document.getElementById('inp-admin-pass').value;
  try {
    const r = await fetch(`${API}/admin/login`, {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({password:p})
    });
    const d = await r.json();
    if(d.ok) {
      adminPass = p;
      closeModal('m-admin-login');
      document.getElementById('inp-admin-pass').value = '';
      loadAdminStats();
      go('s-admin');
    } else { toast("Parol noto'g'ri", "err"); }
  } catch(e) { toast("Xatolik", "err"); }
}

function switchAdminTab(t) {
  ['stats','users','payments','settings'].forEach(x => {
    document.getElementById(`tab-${x}`).classList.remove('act');
    document.getElementById(`pnl-${x}`).classList.remove('act');
  });
  document.getElementById(`tab-${t}`).classList.add('act');
  document.getElementById(`pnl-${t}`).classList.add('act');
  if(t==='stats') loadAdminStats();
  if(t==='users') loadAdminUsers();
  if(t==='payments') loadAdminPayments();
  if(t==='settings') loadAdminSettings();
}

async function loadAdminStats(){
  try {
    const r = await fetch(`${API}/admin/stats?password=${adminPass}`);
    const d = await r.json();
    document.getElementById('st-total').textContent = d.total_users;
    document.getElementById('st-active').textContent = d.active_subs;
    document.getElementById('st-exp').textContent = d.expired_subs;
    document.getElementById('st-rev').textContent = d.monthly_revenue.toLocaleString('uz-UZ') + " UZS";
  } catch(e){}
}

async function loadAdminUsers(){
  try {
    const r = await fetch(`${API}/admin/users?password=${adminPass}`);
    const d = await r.json();
    const el = document.getElementById('admin-users-list');
    const now = Date.now() / 1000;
    el.innerHTML = Object.entries(d).map(([uid, u]) => {
      const active = (u.expires_at || 0) > now;
      const statusStr = active ? '<span style="color:var(--success)">Aktiv</span>' : '<span style="color:var(--danger)">Muddati tugagan</span>';
      return `
      <div class="user-row">
        <strong>${u.name || 'Ismsiz'} (@${u.username || ''})</strong>
        <span>ID: ${uid}</span>
        <span>Tel: ${u.phone || 'yoq'}</span>
        <span>Status: ${statusStr}</span>
      </div>`;
    }).join('');
  } catch(e){}
}

async function loadAdminPayments(){
  try {
    const r = await fetch(`${API}/admin/payments?password=${adminPass}`);
    const d = await r.json();
    const el = document.getElementById('admin-pay-list');
    el.innerHTML = Object.entries(d).map(([suffix, p]) => `
      <div class="pay-box">
        <strong>Summa: ${p.amount.toLocaleString('uz-UZ')} so'm</strong>
        <span>Foydalanuvchi: ${p.name} (${p.user_id})</span>
        <span>Muddati: ${p.months} oy</span>
        <div style="display:flex; gap:8px; margin-top:10px">
          <button class="btn btn-p" style="padding:8px" onclick="approvePay('${suffix}')">Tasdiqlash</button>
          <button class="btn btn-o" style="padding:8px; color:var(--danger)" onclick="rejectPay('${suffix}')">Rad etish</button>
        </div>
      </div>
    `).join('');
    if(Object.keys(d).length === 0) el.innerHTML = '<div style="text-align:center; color:var(--muted); padding:20px">Kutilayotgan to\\'lovlar yo\\'q</div>';
  } catch(e){}
}

async function approvePay(suffix){
  try {
    await fetch(`${API}/admin/payments/approve?suffix=${suffix}&password=${adminPass}`, {method:'POST'});
    toast("Tasdiqlandi!", "ok"); loadAdminPayments();
  } catch(e){}
}
async function rejectPay(suffix){
  try {
    await fetch(`${API}/admin/payments/reject?suffix=${suffix}&password=${adminPass}`, {method:'POST'});
    toast("Rad etildi!", "ok"); loadAdminPayments();
  } catch(e){}
}

async function loadAdminSettings(){
  try {
    const r = await fetch(`${API}/admin/settings?password=${adminPass}`);
    const d = await r.json();
    document.getElementById('adm-set-pass').value = d.password;
    document.getElementById('adm-set-channel').value = d.channel_id;
    document.getElementById('adm-set-price').value = d.monthly_price;
  } catch(e){}
}

async function saveAdminSettings(){
  try {
    await fetch(`${API}/admin/settings?password=${adminPass}`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        password: document.getElementById('adm-set-pass').value,
        channel_id: document.getElementById('adm-set-channel').value,
        monthly_price: parseInt(document.getElementById('adm-set-price').value) || 15000
      })
    });
    toast("Saqlandi!", "ok");
    adminPass = document.getElementById('adm-set-pass').value;
  } catch(e){}
}

"""
html = html.replace('// ═══════════════════════════════\n// STATE\n// ═══════════════════════════════', js_inject + '\n// ═══════════════════════════════\n// STATE\n// ═══════════════════════════════')

html = html.replace("if(id==='s-home') loadHomeStatus();", "if(id==='s-home') { loadHomeStatus(); checkSubStatus(); }")
html = html.replace("loadHomeStatus();\n</script>", "loadHomeStatus();\ncheckSubStatus();\n</script>")

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("Frontend index.html patched successfully.")
