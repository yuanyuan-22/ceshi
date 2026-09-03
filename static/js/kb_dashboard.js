let currentUserRole = null;

function showLoginPanel() {
  const panel = document.getElementById('kb_login_panel');
  if (panel) panel.style.display = 'flex';
}

function hideLoginPanel() {
  const panel = document.getElementById('kb_login_panel');
  if (panel) panel.style.display = 'none';
}

async function kbLogin() {
  const username = document.getElementById('kb_login_user').value;
  const password = document.getElementById('kb_login_pwd').value;
  const errorEl = document.getElementById('kb_login_error');
  
  if (!username || !password) {
    errorEl.textContent = '请输入用户名和密码';
    return;
  }
  
  try {
    const res = await fetch('/api/auth/login/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });
    
    if (!res.ok) {
      errorEl.textContent = '登录失败，请检查用户名和密码';
      return;
    }
    
    const data = await res.json();
    localStorage.setItem('jwt_access', data.access);
    localStorage.setItem('jwt_refresh', data.refresh);
    
    hideLoginPanel();
    initKB();
  } catch (e) {
    errorEl.textContent = '登录请求失败';
  }
}

async function kbRegister() {
  const username = document.getElementById('kb_login_user').value;
  const password = document.getElementById('kb_login_pwd').value;
  const errorEl = document.getElementById('kb_login_error');
  
  if (!username || !password) {
    errorEl.textContent = '请输入用户名和密码';
    return;
  }
  
  try {
    const res = await fetch('/api/auth/register/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });
    
    if (!res.ok) {
      const data = await res.json();
      errorEl.textContent = data.error || '注册失败';
      return;
    }
    
    errorEl.style.color = 'green';
    errorEl.textContent = '注册成功，请登录';
    setTimeout(() => {
      errorEl.style.color = '#e11d48';
      kbLogin();
    }, 1000);
  } catch (e) {
    errorEl.textContent = '注册请求失败';
  }
}

async function initKB() {
  const token = getToken();
  if (!token) {
    showLoginPanel();
    return;
  }
  
  try {
    const meRes = await authFetch('/api/auth/me/', { method: 'GET' });
    if (!meRes.ok) {
      showLoginPanel();
      return;
    }
    const me = await meRes.json();
    currentUserRole = (me.is_staff || me.is_superuser) ? 'admin' : 'user';
    
    const badge = document.getElementById('kbRoleBadge');
    if (badge) badge.textContent = currentUserRole;
    
    const isAdmin = currentUserRole === 'admin';
    const fileInput = document.getElementById('kb_file');
    const textArea = document.getElementById('kb_text');
    if (fileInput) fileInput.disabled = !isAdmin;
    if (textArea) textArea.disabled = !isAdmin;
    
    loadEntities();
    loadUploadList();
  } catch (e) {
    console.error('initKB error', e);
    showLoginPanel();
  }
}

document.addEventListener('DOMContentLoaded', () => {
  initKB();
});

function kbUpload() {
  const fileInput = document.getElementById('kb_file');
  const textArea = document.getElementById('kb_text');
  const f = fileInput.files[0];
  const text = textArea.value;
  
  if (f) {
    const form = new FormData();
    form.append('file', f);
    authFetch('/api/kb/upload/', { method: 'POST', body: form })
      .then(r => r.json())
      .then(d => {
        alert(JSON.stringify(d));
        loadUploadList();
      });
  } else if (text.trim()) {
    authFetch('/api/kb/upload/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    }).then(r => r.json()).then(d => {
      loadUploadList();
      textArea.value = '';
    });
  } else {
    alert('请提供文本或文件');
  }
}

function loadUploadList() {
  authFetch('/api/kb/upload_list/')
    .then(res => res.json())
    .then(list => {
      const el = document.getElementById('kbUploadList');
      if (!el) return;
      el.innerHTML = '';
      (list || []).forEach(it => {
        const li = document.createElement('li');
        li.textContent = 'ID:' + it.id + ' status:' + it.status;
        li.style.cursor = 'pointer';
        li.onclick = function() {
          document.getElementById('uploadStatus').textContent = 'Selected: ' + it.id;
          authFetch('/api/kb/process/' + it.id + '/', { method: 'POST' })
            .then(r => r.json())
            .then(d => { loadEntities(); });
        };
        el.appendChild(li);
      });
    });
}

function kbLoadEntities() {
  loadEntities();
}

function loadEntities() {
  authFetch('/api/kb/entities/')
    .then(res => res.json())
    .then(list => {
      const el = document.getElementById('kbEntities');
      if (!el) return;
      el.innerHTML = '';
      (list || []).forEach(e => {
        const div = document.createElement('div');
        div.style.border = '1px solid #ddd';
        div.style.padding = '6px';
        div.style.marginBottom = '6px';
        div.style.cursor = 'pointer';
        div.textContent = e.entity_key || e.id;
        div.onclick = function() {
          authFetch('/api/kb/entities/' + e.id + '/')
            .then(r => r.json())
            .then(data => {
              const pre = document.getElementById('kbEntityJson');
              if (pre) pre.textContent = JSON.stringify(data, null, 2);
              loadTermCardsForSelected(e.id);
            });
        };
        el.appendChild(div);
      });
      if (list && list.length > 0) {
        loadTermCardsForSelected(list[0].id);
      }
    });
}

function loadTermCardsForSelected(entity_id) {
  if (!entity_id) return;
  authFetch('/api/kb/entities/' + entity_id + '/term_cards/')
    .then(res => res.json())
    .then(cards => {
      const container = document.getElementById('kbTermCardsPreview');
      if (!container) return;
      if (!cards || !cards.length) {
        container.innerHTML = '<div class="empty-box">（暂无术语卡片）</div>';
        return;
      }
      container.innerHTML = cards.map(c => `<div class="term-card" style="padding:8px; border:1px solid #e2e8f0; border-radius:6px; margin-bottom:6px;">
        <div><strong>${c.lang || ''}:</strong> ${c.term || ''}</div>
        <div style="font-size:12px; color:#4b5563;">${c.explain || ''}</div>
      </div>`).join('');
    });
}

function buildMultilang() {
  authFetch('/api/kb/build_multilang/', { method: 'POST' })
    .then(r => r.json())
    .then(d => {
      const statusEl = document.getElementById('kbBuildStatus');
      if (statusEl) statusEl.textContent = d.status || 'done';
    });
}

function generateTrainingData() {
  authFetch('/api/kb/generate_training_data/', { method: 'POST' })
    .then(r => r.json())
    .then(d => { console.log(d); });
}
