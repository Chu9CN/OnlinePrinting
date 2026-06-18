const API_BASE = '/api';

// ========== 认证与基础工具 ==========

function getToken() { return localStorage.getItem('token'); }

function getHeaders() {
    return { 'Authorization': `Bearer ${getToken()}`, 'Content-Type': 'application/json' };
}

function logout() {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    window.location.href = 'login.html';
}

function formatDate(isoStr) {
    if (!isoStr) return '-';
    const d = new Date(isoStr);
    return d.toLocaleDateString('zh-CN') + ' ' + d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
}

// ========== 弹窗 ==========

function closeModal(id) { document.getElementById(id).style.display = 'none'; }

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', e => { if (e.target === modal) modal.style.display = 'none'; });
    });
});

// ========== Toast ==========

function showToast(msg, type = 'info') {
    const toast = document.getElementById('toast');
    if (!toast) return;
    toast.textContent = msg;
    toast.className = `toast show ${type}`;
    setTimeout(() => toast.classList.remove('show'), 3000);
}

// ========== 主题切换 ==========

function toggleTheme() {
    const html = document.documentElement;
    const isDark = html.getAttribute('data-theme') === 'dark';
    const next = isDark ? 'light' : 'dark';
    html.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
    const icon = document.getElementById('themeIcon');
    if (icon) icon.className = isDark ? 'ri-moon-line' : 'ri-sun-line';
}

(function initTheme() {
    const saved = localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', saved);
    const icon = document.getElementById('themeIcon');
    if (icon) icon.className = saved === 'dark' ? 'ri-sun-line' : 'ri-moon-line';
})();

// ========== 接管浏览器弹窗 ==========

(function () {
    const ov = document.getElementById('customDialog');
    if (!ov) return;
    const icon = document.getElementById('dialogIcon'),
          msg  = document.getElementById('dialogMessage'),
          input= document.getElementById('dialogInput'),
          btnOk= document.getElementById('dialogOk'),
          btnCancel = document.getElementById('dialogCancel');
    let resolver = null, curType = null;

    function show(type, txt, iconHtml, iconCls, withInput, defVal) {
        return new Promise(resolve => {
            curType = type; resolver = resolve;
            msg.textContent = txt;
            icon.className = 'dialog-icon ' + iconCls;
            icon.innerHTML = iconHtml;
            input.style.display = withInput ? 'block' : 'none';
            if (withInput) { input.value = defVal || ''; input.focus(); input.select(); }
            btnCancel.style.display = type === 'alert' ? 'none' : '';
            ov.style.display = 'flex';
            if (!withInput) btnOk.focus();
        });
    }

    btnOk.addEventListener('click', () => {
        ov.style.display = 'none';
        resolver(curType === 'prompt' ? input.value : true);
    });
    btnCancel.addEventListener('click', () => {
        ov.style.display = 'none';
        resolver(curType === 'prompt' ? null : false);
    });
    input.addEventListener('keydown', e => {
        if (e.key === 'Enter') btnOk.click();
        else if (e.key === 'Escape') btnCancel.click();
    });
    document.addEventListener('keydown', e => {
        if (ov.style.display !== 'flex') return;
        if (e.key === 'Escape') btnCancel.click();
        else if (e.key === 'Enter' && curType !== 'prompt') btnOk.click();
    });

    window.alert   = m => show('alert',   String(m||''), '<i class="ri-information-line"></i>', 'info', false);
    window.confirm = m => show('confirm', String(m||''), '<i class="ri-question-line"></i>', 'confirm', false);
    window.prompt  = (m, d) => show('prompt', String(m||''), '<i class="ri-edit-line"></i>', 'info', true, d||'');
})();
