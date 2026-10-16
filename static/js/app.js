/**
 * Raiganj University Notice & SMTP Dispatcher
 * Frontend Application Controller
 */

let allStudents = [];
let allNotices = [];
let currentCategoryFilter = 'ALL';
let currentLogLevelFilter = 'ALL';
let countdownInterval = null;
let currentCountdownSeconds = 0;
let currentLiveNotice = null;
let currentModalNoticeId = null;

// ----------------- Separate Dark & Light Theme Controller ----------------- //
function initTheme() {
  const saved = localStorage.getItem('rgu_theme') || 'dark';
  setTheme(saved);
}

function setTheme(mode) {
  const targetTheme = (mode === 'light') ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', targetTheme);
  localStorage.setItem('rgu_theme', targetTheme);

  // Synchronize separate segmented buttons in navbar
  const btnDark = document.getElementById('btnThemeDark');
  const btnLight = document.getElementById('btnThemeLight');
  if (btnDark) btnDark.classList.toggle('active', targetTheme === 'dark');
  if (btnLight) btnLight.classList.toggle('active', targetTheme === 'light');

  // Maintain backwards compatibility for single toggle button if present
  const icon = document.getElementById('themeToggleIcon');
  if (icon) {
    icon.className = targetTheme === 'light' ? 'fa-solid fa-moon' : 'fa-solid fa-sun';
  }
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
  setTheme(current === 'light' ? 'dark' : 'light');
}

// ----------------- Refined Clean Hover Physics (Stable, Executive) ----------------- //
function initMouseHoverEffects() {
  // Stable, zero-wobble executive hover experience
}

document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initApp();
});

async function initApp() {
  initTheme();
  await fetchSystemStatus();
  await loadRecentAiNotice();
  await loadStudents();
  await loadNotices();
  await loadSmtpConfig();
  await loadLocalInbox();
  await loadLogs();
  await loadDispatches();

  // Background polling every 8 seconds for real-time updates
  setInterval(fetchSystemStatus, 8000);
  setInterval(loadLocalInbox, 12000);
}

// ----------------- Tab Navigation ----------------- //
function switchTab(tabId) {
  document.querySelectorAll('.tab-btn, .nav-tab').forEach(t => {
    t.classList.toggle('active', t.getAttribute('data-tab') === tabId);
  });
  document.querySelectorAll('.tab-pane').forEach(p => {
    p.classList.toggle('active', p.id === `tab-${tabId}`);
  });

  if (tabId === 'students') loadStudents();
  if (tabId === 'notices') loadNotices();
  if (tabId === 'smtp') {
    loadSmtpConfig();
    loadLocalInbox();
  }
  if (tabId === 'logs') loadLogs();
}

// ----------------- System Status & Countdown ----------------- //
async function fetchSystemStatus() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();

    // Update Metrics
    document.getElementById('metricTotalStudents').innerText = data.stats.total_students || 0;
    document.getElementById('metricActiveStudents').innerText = data.stats.active_students || 0;
    document.getElementById('metricTotalNotices').innerText = data.stats.total_notices || 0;

    const audienceElem = document.getElementById('metricGroupAudience');
    if (audienceElem) {
      audienceElem.innerText = data.google_group_email ? '1,000+' : (data.stats.total_students || 0);
    }
    const groupLinkElem = document.getElementById('metricGroupEmailLink');
    if (groupLinkElem && data.google_group_email) {
      groupLinkElem.innerText = data.google_group_email;
    }

    // Badges in header
    document.getElementById('navStudentCount').innerText = data.stats.total_students || 0;
    document.getElementById('navNoticeCount').innerText = data.stats.total_notices || 0;

    const pendingCount = data.stats.pending_notices || 0;
    const pendingBadge = document.getElementById('pendingQueueCount');
    if (pendingBadge) {
      pendingBadge.innerText = pendingCount;
    }
    const btnDeliver = document.getElementById('btnDeliverPending');
    if (btnDeliver) {
      if (pendingCount > 0) {
        btnDeliver.classList.add('has-pending');
      } else {
        btnDeliver.classList.remove('has-pending');
      }
    }

    // Google Group Badge in header
    const smtpBadgeText = document.getElementById('smtpBadgeText');
    if (smtpBadgeText) {
      if (data.google_group_email) {
        smtpBadgeText.innerHTML = `<i class="fa-solid fa-users"></i> ${escapeHtml(data.google_group_email)}`;
      } else {
        smtpBadgeText.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> Group Email Required`;
      }
    }

    // Dashboard info card
    document.getElementById('dashLastRun').innerText = data.stats.last_scraped_at || 'Never executed yet';
    document.getElementById('dashNextRun').innerText = data.scheduler.next_run || '7:00 AM / 7:00 PM IST';
    document.getElementById('dashSmtpChannel').innerText = data.google_group_email 
      ? `Google Groups Broadcast (${data.google_group_email})` 
      : `Google Groups Broadcast (Setup Required)`;
    document.getElementById('dashStudentAudience').innerText = data.google_group_email
      ? `All 1,000+ members in Google Group`
      : `${data.stats.active_students} active enrolled student(s)`;
    document.getElementById('metricNextRunText').innerText = `Next run: ${data.scheduler.next_run || '7:00 AM/PM IST'}`;

    // Update Countdown
    if (data.scheduler && typeof data.scheduler.countdown_seconds === 'number') {
      currentCountdownSeconds = data.scheduler.countdown_seconds;
      startCountdownClock();
    }
  } catch (err) {
    console.warn('Status fetch error:', err);
  }
}

function startCountdownClock() {
  if (countdownInterval) clearInterval(countdownInterval);

  updateCountdownDisplay();
  countdownInterval = setInterval(() => {
    if (currentCountdownSeconds > 0) {
      currentCountdownSeconds--;
      updateCountdownDisplay();
    } else {
      // Reached target time! Trigger status refresh
      fetchSystemStatus();
    }
  }, 1000);
}

function updateCountdownDisplay() {
  const hours = Math.floor(currentCountdownSeconds / 3600);
  const minutes = Math.floor((currentCountdownSeconds % 3600) / 60);
  const seconds = currentCountdownSeconds % 60;

  const pad = (n) => String(n).padStart(2, '0');
  const formatted = `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
  const timerElem = document.getElementById('countdownTimer');
  if (timerElem) timerElem.innerText = formatted;
}

// ----------------- Scraper Manual Trigger ----------------- //
async function triggerScanNow() {
  const btn = document.getElementById('btnQuickScan');
  const origHtml = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> <span>Scraping RGU...</span>`;

  showToast('Connecting to raiganjuniversity.ac.in & scanning for notices...', 'info');

  try {
    const res = await fetch('/api/notices/scan-now', { method: 'POST' });
    const data = await res.json();

    if (data.status === 'success') {
      showToast(`Scrape completed! Found ${data.new_count} new notice(s) and emailed students!`, 'success');
    } else if (data.status === 'no_new') {
      showToast(`Scan complete: No new notices found. Total tracked: ${data.total_scraped}. Next check at 7:00 AM/PM IST.`, 'info');
    } else {
      showToast(data.message || 'Scrape completed with notice check.', 'info');
    }

    await fetchSystemStatus();
    await loadRecentAiNotice();
    await loadNotices();
    await loadLocalInbox();
    await loadLogs();
    await loadDispatches();
  } catch (err) {
    showToast('Failed to trigger scan: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = origHtml;
  }
}

// ----------------- Students Controller ----------------- //
async function loadStudents() {
  try {
    const res = await fetch('/api/students');
    const data = await res.json();
    allStudents = data.students || [];
    renderStudentsTable(allStudents);
    document.getElementById('studentTableCount').innerText = allStudents.length;
  } catch (err) {
    console.error('Error loading students:', err);
  }
}

function renderStudentsTable(students) {
  const tbody = document.getElementById('studentsTableBody');
  if (!students || students.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="7" class="empty-cell">
          <i class="fa-solid fa-user-slash" style="font-size: 24px; margin-bottom: 8px; display: block;"></i>
          No student email addresses enrolled yet.<br>
          Click <strong>"Add Student"</strong> or <strong>"Load Demo Students"</strong> to populate.
        </td>
      </tr>`;
    return;
  }

  tbody.innerHTML = students.map(s => {
    const initials = (s.name || 'S').split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
    return `
      <tr>
        <td>
          <div class="student-name-box">
            <span class="student-avatar">${initials}</span>
            <strong>${escapeHtml(s.name)}</strong>
          </div>
        </td>
        <td><code>${escapeHtml(s.email)}</code></td>
        <td><span class="badge badge-neutral">${escapeHtml(s.department || 'General')}</span></td>
        <td><span style="font-family: var(--font-mono); font-size: 12px;">${escapeHtml(s.roll_no || '—')}</span></td>
        <td>
          <label class="status-toggle" title="Toggle active subscription">
            <input type="checkbox" ${s.is_active ? 'checked' : ''} onchange="toggleStudentActive(${s.id}, this.checked)">
            <span class="slider"></span>
          </label>
          <span style="margin-left: 8px; font-size: 12px; color: ${s.is_active ? 'var(--emerald)' : 'var(--text-tertiary)'};">
            ${s.is_active ? 'Subscribed' : 'Paused'}
          </span>
        </td>
        <td style="font-size: 12px; color: var(--text-subtle);">${s.created_at || 'Recent'}</td>
        <td>
          <button class="btn btn-icon text-danger" title="Delete Student" onclick="deleteStudent(${s.id}, '${escapeHtml(s.name)}')">
            <i class="fa-solid fa-trash-can"></i>
          </button>
        </td>
      </tr>`;
  }).join('');
}

function handleStudentSearch() {
  const query = document.getElementById('studentSearchInput').value.toLowerCase().trim();
  const filtered = allStudents.filter(s => 
    s.name.toLowerCase().includes(query) ||
    s.email.toLowerCase().includes(query) ||
    (s.department && s.department.toLowerCase().includes(query)) ||
    (s.roll_no && s.roll_no.toLowerCase().includes(query))
  );
  renderStudentsTable(filtered);
  document.getElementById('studentTableCount').innerText = filtered.length;
}

async function toggleStudentActive(studentId, isActive) {
  try {
    const res = await fetch(`/api/students/${studentId}/status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_active: isActive ? 1 : 0 })
    });
    if (res.ok) {
      showToast(`Student alert status updated.`, 'info');
      fetchSystemStatus();
    }
  } catch (err) {
    showToast('Failed to update status', 'error');
  }
}

async function deleteStudent(studentId, name) {
  if (!confirm(`Are you sure you want to remove ${name} from receiving university alerts?`)) return;

  try {
    const res = await fetch(`/api/students/${studentId}`, { method: 'DELETE' });
    if (res.ok) {
      showToast(`Removed student ${name}`, 'info');
      loadStudents();
      fetchSystemStatus();
    }
  } catch (err) {
    showToast('Failed to delete student', 'error');
  }
}

async function submitAddStudent(e) {
  e.preventDefault();
  const name = document.getElementById('newStudentName').value.trim();
  const email = document.getElementById('newStudentEmail').value.trim();
  const department = document.getElementById('newStudentDept').value.trim();
  const roll_no = document.getElementById('newStudentRoll').value.trim();

  try {
    const res = await fetch('/api/students', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email, department, roll_no })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`Enrolled ${name} (${email}) successfully!`, 'success');
      closeModal('addStudentModal');
      document.getElementById('addStudentForm').reset();
      loadStudents();
      fetchSystemStatus();
    } else {
      showToast(data.error || 'Failed to add student', 'error');
    }
  } catch (err) {
    showToast('Error: ' + err.message, 'error');
  }
}

async function submitBulkStudents(e) {
  e.preventDefault();
  const raw_data = document.getElementById('bulkDataInput').value.trim();
  if (!raw_data) return;

  try {
    const res = await fetch('/api/students/bulk', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ raw_data })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`Imported ${data.added} students (${data.skipped} duplicates skipped)`, 'success');
      closeModal('bulkStudentModal');
      document.getElementById('bulkStudentForm').reset();
      loadStudents();
      fetchSystemStatus();
    }
  } catch (err) {
    showToast('Import error: ' + err.message, 'error');
  }
}

async function seedSampleStudents() {
  try {
    const res = await fetch('/api/students/seed-sample', { method: 'POST' });
    const data = await res.json();
    showToast(`Loaded ${data.added} demo students!`, 'success');
    loadStudents();
    fetchSystemStatus();
  } catch (err) {
    showToast('Error seeding students', 'error');
  }
}

// ----------------- Notices Controller ----------------- //
async function loadNotices() {
  try {
    const res = await fetch('/api/notices?limit=100');
    const data = await res.json();
    allNotices = data.notices || [];
    renderNoticesTable(allNotices);
    renderDashboardNotices(allNotices.slice(0, 6));

    // Update Live Email Preview with first notice if available
    if (allNotices.length > 0) {
      const top = allNotices[0];
      document.getElementById('mockupSubject').innerText = `Subject: [RGU Notice #${top.id}] ${top.title}`;
      document.getElementById('mockupTitle').innerText = top.title;
      document.getElementById('mockupId').innerText = `Notice #${top.id}`;
      document.getElementById('mockupCategory').innerText = top.category || 'Notice';
      document.getElementById('mockupDate').innerText = top.published_on || 'Today';
    }
  } catch (err) {
    console.error('Error loading notices:', err);
  }
}

function renderNoticesTable(notices) {
  const tbody = document.getElementById('noticesTableBody');
  if (!notices || notices.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" class="empty-cell">
          <i class="fa-solid fa-magnifying-glass" style="font-size: 24px; margin-bottom: 8px; display: block;"></i>
          No notices stored in the local cache yet.<br>
          Click <strong>"Scan Website Now"</strong> to fetch latest notices from Raiganj University.
        </td>
      </tr>`;
    return;
  }

function renderNoticeStatusBadge(status) {
  if (status === 'sent') {
    return `<span class="badge badge-status status-sent" title="Delivered to Google Group"><span class="status-dot dot-emerald"></span> Delivered</span>`;
  } else if (status === 'failed') {
    return `<span class="badge badge-status status-failed" title="Delivery failed on last attempt"><span class="status-dot dot-rose"></span> Failed</span>`;
  } else {
    return `<span class="badge badge-status status-queued" title="Queued for automated delivery"><span class="status-dot dot-amber"></span> Queued</span>`;
  }
}

  tbody.innerHTML = notices.map(n => {
    return `
      <tr>
        <td><span class="notice-id-chip">#${escapeHtml(n.id)}</span></td>
        <td>
          <div style="display: flex; align-items: center; gap: 10px;">
            <img src="/static/images/logo.png" alt="RGU" style="width: 26px; height: 26px; border-radius: 6px; background: #ffffff; padding: 2px; flex-shrink: 0; box-shadow: 0 2px 6px rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.15);">
            <a href="${escapeHtml(n.link)}" target="_blank" class="accent-link" style="font-weight: 600;">
              ${escapeHtml(n.title)}
            </a>
          </div>
        </td>
        <td><span class="badge badge-neutral">${escapeHtml(n.category || 'General')}</span></td>
        <td style="font-size: 12.5px; color: var(--text-muted);">${escapeHtml(n.published_on || '—')}</td>
        <td>
          ${renderNoticeStatusBadge(n.email_status)}
        </td>
        <td>
          <div style="display: flex; gap: 6px;">
            <button class="btn btn-secondary btn-xs btn-ai" title="View Gemini Polished Announcement & Markdown" onclick="openNoticeAiModal('${n.id}')">
              <i class="fa-solid fa-wand-magic-sparkles"></i> View Polish
            </button>
            <a href="${escapeHtml(n.link)}" target="_blank" class="btn btn-icon" title="Open on Raiganj University Portal">
              <i class="fa-solid fa-arrow-up-right-from-square"></i>
            </a>
            <button class="btn btn-icon" title="Broadcast notice to Google Group" onclick="resendNotice('${n.id}', '${escapeHtml(n.title)}')">
              <i class="fa-solid fa-paper-plane"></i>
            </button>
            ${n.email_status !== 'pending' && n.email_status !== 'sent' ? `
            <button class="btn btn-icon" title="Queue this notice for automatic delivery" onclick="queueNoticeForDelivery('${n.id}')">
              <i class="fa-solid fa-plus"></i>
            </button>` : ''}
          </div>
        </td>
      </tr>`;
  }).join('');
}

function renderDashboardNotices(notices) {
  const tbody = document.getElementById('dashNoticesTableBody');
  if (!notices || notices.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="5" class="empty-cell">
          No notices cached yet. Click "Check Notices Now" to scrape from RGU.
        </td>
      </tr>`;
    return;
  }

  tbody.innerHTML = notices.map(n => `
    <tr>
      <td><span class="notice-id-chip">#${escapeHtml(n.id)}</span></td>
      <td>
        <div style="display: flex; align-items: center; gap: 8px;">
          <img src="/static/images/logo.png" alt="RGU" style="width: 22px; height: 22px; border-radius: 5px; background: #ffffff; padding: 2px; flex-shrink: 0; box-shadow: 0 1px 4px rgba(0,0,0,0.25);">
          <a href="${escapeHtml(n.link)}" target="_blank" class="accent-link" style="font-weight: 500;">
            ${escapeHtml(n.title)}
          </a>
        </div>
      </td>
      <td><span class="badge badge-neutral">${escapeHtml(n.category || 'General')}</span></td>
      <td style="font-size: 12px; color: var(--text-muted);">${escapeHtml(n.published_on || '—')}</td>
      <td>
        <div style="display: flex; gap: 6px;">
          <button class="btn btn-secondary btn-xs btn-ai" onclick="openNoticeAiModal('${n.id}')" title="Inspect Gemini Polish">
            <i class="fa-solid fa-wand-magic-sparkles"></i> View Polish
          </button>
          <button class="btn btn-secondary btn-xs" onclick="resendNotice('${n.id}', '${escapeHtml(n.title)}')">
            <i class="fa-solid fa-paper-plane"></i> Send
          </button>
        </div>
      </td>
    </tr>
  `).join('');
}

function filterNoticeCat(cat) {
  currentCategoryFilter = cat;
  document.querySelectorAll('#noticeCategoryFilters .filter-chip, #noticeCategoryFilters .filter-pill').forEach(p => {
    p.classList.toggle('active', p.innerText.toLowerCase().includes(cat.toLowerCase()) || (cat === 'ALL' && p.innerText === 'All'));
  });
  applyNoticeFilters();
}

function handleNoticeSearch() {
  applyNoticeFilters();
}

function applyNoticeFilters() {
  const search = document.getElementById('noticeSearchInput').value.toLowerCase().trim();
  const filtered = allNotices.filter(n => {
    const matchesSearch = n.title.toLowerCase().includes(search) || n.id.toLowerCase().includes(search);
    const matchesCat = currentCategoryFilter === 'ALL' || (n.category && n.category.toLowerCase().includes(currentCategoryFilter.toLowerCase()));
    return matchesSearch && matchesCat;
  });
  renderNoticesTable(filtered);
}

async function resendNotice(noticeId, title) {
  if (!confirm(`Dispatch notice "${title}" to all active enrolled students?`)) return;

  showToast(`Dispatching notice #${noticeId} to active students...`, 'info');
  try {
    const res = await fetch(`/api/notices/${noticeId}/resend`, { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      showToast(`Successfully emailed to ${data.sent_count} student(s)!`, 'success');
      loadNotices();
      fetchSystemStatus();
      loadLocalInbox();
      loadLogs();
      loadDispatches();
    } else {
      showToast(data.message || 'Dispatch failed', 'error');
    }
  } catch (err) {
    showToast('Failed to dispatch notice: ' + err.message, 'error');
  }
}

async function queueNoticeForDelivery(noticeId) {
  showToast(`Queueing Notice #${noticeId} for automated delivery...`, 'info');
  try {
    const res = await fetch(`/api/notices/${noticeId}/mark-pending`, { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, 'success');
      await loadNotices();
      await fetchSystemStatus();
    } else {
      showToast(data.message || 'Failed to queue notice', 'error');
    }
  } catch (err) {
    showToast('Queue error: ' + err.message, 'error');
  }
}

async function dispatchPendingNow() {
  const btn = document.getElementById('btnDeliverPending');
  const origHtml = btn ? btn.innerHTML : '';
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> <span>Delivering...</span>`;
  }

  showToast('Checking pending queue and delivering emails to students...', 'info');

  try {
    const res = await fetch('/api/notices/dispatch-pending', { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      if (data.sent_count > 0) {
        showToast(`Delivered ${data.sent_count} pending notice(s) to students / Google Group!`, 'success');
      } else {
        showToast(data.message || 'No pending notices waiting. All up to date!', 'info');
      }
      await loadNotices();
      await fetchSystemStatus();
      await loadDispatches();
      await loadLogs();
    } else {
      showToast(data.message || 'Dispatch failed', 'error');
    }
  } catch (err) {
    showToast('Failed to dispatch pending notices: ' + err.message, 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = origHtml;
    }
  }
}

// ----------------- Google Group Broadcast & Settings ----------------- //
function togglePasswordVisibility(inputId, btn) {
  const input = document.getElementById(inputId);
  if (!input) return;
  if (input.type === 'password') {
    input.type = 'text';
    btn.innerHTML = '<i class="fa-regular fa-eye-slash"></i>';
  } else {
    input.type = 'password';
    btn.innerHTML = '<i class="fa-regular fa-eye"></i>';
  }
}

async function loadSmtpConfig() {
  try {
    const res = await fetch('/api/smtp/config');
    const cfg = await res.json();

    if (document.getElementById('smtpGoogleGroupEmail')) {
      document.getElementById('smtpGoogleGroupEmail').value = cfg.google_group_email || '';
    }
    if (document.getElementById('smtpSenderEmail')) {
      document.getElementById('smtpSenderEmail').value = cfg.sender_email || cfg.custom_username || '';
    }
    if (document.getElementById('smtpSenderName')) {
      document.getElementById('smtpSenderName').value = cfg.sender_name || 'Raiganj University Notice Board';
    }
    if (document.getElementById('smtpCustomPass')) {
      document.getElementById('smtpCustomPass').value = cfg.custom_password_masked || '';
    }
    if (document.getElementById('smtpGeminiKey')) {
      document.getElementById('smtpGeminiKey').value = cfg.gemini_api_key_masked || '';
    }
    if (document.getElementById('smtpCustomHost')) {
      document.getElementById('smtpCustomHost').value = cfg.custom_host || 'smtp.gmail.com';
    }
    if (document.getElementById('smtpCustomPort')) {
      document.getElementById('smtpCustomPort').value = cfg.custom_port || 587;
    }
    if (document.getElementById('smtpCustomTls')) {
      document.getElementById('smtpCustomTls').checked = cfg.custom_use_tls !== 0;
    }
    if (document.getElementById('smtpCustomSsl')) {
      document.getElementById('smtpCustomSsl').checked = !!cfg.custom_use_ssl;
    }

    const badge = document.getElementById('currentSmtpModeBadge');
    if (badge) {
      if (cfg.google_group_email) {
        badge.innerHTML = `<i class="fa-solid fa-users"></i> ${escapeHtml(cfg.google_group_email)}`;
      } else {
        badge.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> Group Email Required`;
      }
    }
  } catch (err) {
    console.error('Error loading Google Group / SMTP config:', err);
  }
}

async function saveSmtpConfig(e) {
  e.preventDefault();

  const googleGroupEmail = document.getElementById('smtpGoogleGroupEmail')?.value.trim() || '';
  const senderEmail = document.getElementById('smtpSenderEmail')?.value.trim() || '';
  const senderName = document.getElementById('smtpSenderName')?.value.trim() || 'Raiganj University Notice Board';
  const customPass = document.getElementById('smtpCustomPass')?.value.trim() || '';
  const geminiKey = document.getElementById('smtpGeminiKey')?.value.trim() || '';
  const customHost = document.getElementById('smtpCustomHost')?.value.trim() || 'smtp.gmail.com';
  const customPort = parseInt(document.getElementById('smtpCustomPort')?.value || '587');
  const customTls = document.getElementById('smtpCustomTls')?.checked ? 1 : 0;
  const customSsl = document.getElementById('smtpCustomSsl')?.checked ? 1 : 0;

  const payload = {
    mode: 'googlegroup',
    google_group_email: googleGroupEmail,
    sender_email: senderEmail,
    custom_username: senderEmail,
    custom_password: customPass,
    sender_name: senderName,
    gemini_api_key: geminiKey,
    custom_host: customHost,
    custom_port: customPort,
    custom_use_tls: customTls,
    custom_use_ssl: customSsl
  };

  try {
    const res = await fetch('/api/smtp/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.success) {
      showToast('Google Group & dispatch settings saved successfully!', 'success');
      loadSmtpConfig();
      fetchSystemStatus();
    } else {
      showToast(data.message || 'Failed to save settings', 'error');
    }
  } catch (err) {
    showToast('Failed to save settings: ' + err.message, 'error');
  }
}

// ----------------- Local SMTP Inbox ----------------- //
async function loadLocalInbox() {
  try {
    const res = await fetch('/api/smtp/inbox?limit=50');
    const data = await res.json();
    renderInboxTable(data.emails || []);
  } catch (err) {
    console.error('Error loading inbox:', err);
  }
}

function renderInboxTable(emails) {
  const tbody = document.getElementById('inboxTableBody');
  if (!emails || emails.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="4" class="empty-cell">
          <i class="fa-solid fa-inbox" style="font-size: 24px; margin-bottom: 8px; display: block;"></i>
          No emails captured by local SMTP server yet.<br>
          Trigger a notice check or send a test email to view captured emails here.
        </td>
      </tr>`;
    return;
  }

  tbody.innerHTML = emails.map(m => `
    <tr>
      <td style="font-size: 12px; color: var(--text-subtle); white-space: nowrap;">${m.received_at || 'Recent'}</td>
      <td style="font-size: 13px;"><code>${escapeHtml(m.recipients || 'student@rgu.ac.in')}</code></td>
      <td style="font-weight: 600; color: var(--text-white);">${escapeHtml(m.subject || '(No Subject)')}</td>
      <td>
        <button class="btn btn-secondary btn-xs" onclick="viewCapturedEmail(${m.id}, '${escapeHtml(m.subject)}')">
          <i class="fa-regular fa-eye"></i> View HTML
        </button>
      </td>
    </tr>
  `).join('');
}

function viewCapturedEmail(msgId, subject) {
  document.getElementById('viewEmailTitle').innerHTML = `<i class="fa-solid fa-envelope"></i> ${escapeHtml(subject)}`;
  document.getElementById('emailIframe').src = `/email-preview/${msgId}`;
  openModal('viewEmailModal');
}

async function clearLocalInbox() {
  if (!confirm('Clear all captured emails from the local SMTP inbox?')) return;
  try {
    await fetch('/api/smtp/inbox', { method: 'DELETE' });
    showToast('Local SMTP inbox cleared.', 'info');
    loadLocalInbox();
    fetchSystemStatus();
  } catch (err) {
    showToast('Failed to clear inbox', 'error');
  }
}

// ----------------- Broadcast Test Modal ----------------- //
function openTestModal() {
  document.getElementById('testResultBox').style.display = 'none';
  const groupEmail = document.getElementById('smtpGoogleGroupEmail')?.value.trim() || '';
  const testInput = document.getElementById('testEmailRecipient');
  if (testInput && groupEmail && !testInput.value) {
    testInput.value = groupEmail;
  }
  openModal('testSmtpModal');
}

async function submitTestSmtp(e) {
  e.preventDefault();
  const test_recipient = document.getElementById('testEmailRecipient').value.trim();
  const btn = document.getElementById('btnRunTest');
  const box = document.getElementById('testResultBox');
  const origHtml = btn.innerHTML;

  btn.disabled = true;
  btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Testing Connection...`;
  box.style.display = 'none';

  try {
    const res = await fetch('/api/smtp/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ test_recipient })
    });
    const data = await res.json();
    box.style.display = 'block';
    if (data.success) {
      box.className = 'test-result-box success';
      box.innerHTML = `<i class="fa-solid fa-circle-check"></i> <strong>SUCCESS:</strong> ${escapeHtml(data.message)}`;
      loadLocalInbox();
      loadLogs();
      fetchSystemStatus();
    } else {
      box.className = 'test-result-box error';
      box.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> <strong>FAILED:</strong> ${escapeHtml(data.message)}`;
    }
  } catch (err) {
    box.style.display = 'block';
    box.className = 'test-result-box error';
    box.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> <strong>ERROR:</strong> ${err.message}`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = origHtml;
  }
}

// ----------------- System Logs ----------------- //
async function loadLogs() {
  try {
    const url = currentLogLevelFilter === 'ALL' ? '/api/logs?limit=80' : `/api/logs?limit=80&level=${currentLogLevelFilter}`;
    const res = await fetch(url);
    const data = await res.json();
    renderLogsConsole(data.logs || []);
  } catch (err) {
    console.error('Error loading logs:', err);
  }
}

function renderLogsConsole(logs) {
  const consoleElem = document.getElementById('logsConsole');
  if (!logs || logs.length === 0) {
    consoleElem.innerHTML = `<div class="log-line"><i class="fa-solid fa-circle-info" style="margin-right: 6px;"></i>No execution logs recorded yet.</div>`;
    return;
  }

  consoleElem.innerHTML = logs.map(l => `
    <div class="log-entry">
      <span class="log-ts">[${l.created_at || 'TIME'}]</span>
      <span class="log-tag ${l.level}">${l.level}</span>
      <span class="log-cat">[${l.category}]</span>
      <span class="log-msg">${escapeHtml(l.message)}</span>
    </div>
  `).join('');
}

function filterLogLevel(level) {
  currentLogLevelFilter = level;
  document.querySelectorAll('#logLevelFilters .filter-chip, #logLevelFilters .filter-pill').forEach(p => {
    p.classList.toggle('active', p.innerText.toUpperCase() === level);
  });
  loadLogs();
}

async function clearSystemLogs() {
  if (!confirm('Clear all execution logs?')) return;
  try {
    await fetch('/api/logs', { method: 'DELETE' });
    showToast('Logs cleared.', 'info');
    loadLogs();
  } catch (err) {
    showToast('Failed to clear logs', 'error');
  }
}

// ----------------- Dispatches Feed ----------------- //
async function loadDispatches() {
  try {
    const res = await fetch('/api/dispatches?limit=10');
    const data = await res.json();
    const feed = document.getElementById('dispatchFeedList');
    const records = data.dispatches || [];

    if (records.length === 0) {
      feed.innerHTML = `<li class="empty-cell" style="padding: 24px !important;">No notice dispatches recorded yet.</li>`;
      return;
    }

    feed.innerHTML = records.map(r => `
      <li class="dispatch-item">
        <div>
          <div class="dispatch-notice-name">Notice #${r.notice_id}: ${escapeHtml(r.notice_title)}</div>
          <div class="dispatch-time">${r.dispatched_at} &bull; Delivered to ${r.recipient_count} student(s)</div>
        </div>
        <span class="badge ${r.status === 'SUCCESS' ? 'badge-success' : 'badge-danger'}">${r.status}</span>
      </li>
    `).join('');
  } catch (err) {
    console.error('Error loading dispatches:', err);
  }
}

// ----------------- Modal Helpers ----------------- //
function openModal(modalId) {
  const m = document.getElementById(modalId);
  if (m) m.classList.add('active');
}

function closeModal(modalId) {
  const m = document.getElementById(modalId);
  if (m) m.classList.remove('active');
}

function openAddStudentModal() {
  openModal('addStudentModal');
}

function openBulkModal() {
  openModal('bulkStudentModal');
}

// Close modals when clicking backdrop
document.addEventListener('click', (e) => {
  if (e.target.classList.contains('modal-overlay') || e.target.classList.contains('modal-backdrop')) {
    e.target.classList.remove('active');
  }
});

// ----------------- Toast Notifications & Keyboard Shortcuts ----------------- //
function showToast(message, type = 'info') {
  const container = document.getElementById('toastContainer');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;

  const icon = type === 'success' ? 'fa-circle-check' : (type === 'error' ? 'fa-circle-xmark' : 'fa-circle-info');
  const iconColor = type === 'success' ? '#34d399' : (type === 'error' ? '#fb7185' : '#38bdf8');
  toast.innerHTML = `
    <i class="fa-solid ${icon}" style="font-size: 1.05rem; color: ${iconColor}; flex-shrink: 0;"></i>
    <span>${escapeHtml(message)}</span>
  `;

  container.appendChild(toast);
  requestAnimationFrame(() => {
    toast.classList.add('show');
  });

  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 400);
  }, 4000);
}

// Close modals on Escape key
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-overlay.active').forEach(m => m.classList.remove('active'));
  }
});

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// ----------------- Live Notice AI & Markdown Showcase Controller ----------------- //

async function loadRecentAiNotice() {
  try {
    const res = await fetch('/api/notices/recent-md');
    const data = await res.json();
    if (!data.success || !data.notice) return;

    currentLiveNotice = data.notice;
    const n = data.notice;

    // Badges & Meta
    const noticeIdElem = document.getElementById('liveNoticeId');
    if (noticeIdElem) noticeIdElem.innerText = `Notice #${n.id}`;

    const aiBadge = document.getElementById('liveAiBadge');
    if (aiBadge) {
      if (n.has_gemini_polish) {
        aiBadge.className = 'badge badge-success';
        aiBadge.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles"></i> ✨ Gemini Polished`;
      } else {
        aiBadge.className = 'badge badge-info';
        aiBadge.innerHTML = `<i class="fa-solid fa-file-lines"></i> 📝 Markdown Extracted`;
      }
    }

    const titleElem = document.getElementById('liveNoticeTitle');
    if (titleElem) titleElem.innerText = n.title;

    const dateElem = document.getElementById('liveNoticeDate');
    if (dateElem) dateElem.innerText = n.published_on || 'Recent';

    const catElem = document.getElementById('liveNoticeCategory');
    if (catElem) catElem.innerText = n.category || 'General';

    const linkElem = document.getElementById('liveNoticeOfficialLink');
    if (linkElem) linkElem.href = n.link;

    // View 1: Gemini Polish HTML & Dedicated Text Field
    const htmlElem = document.getElementById('livePolishedHtml');
    if (htmlElem) {
      htmlElem.innerHTML = n.polished_html || `<p>${escapeHtml(n.polished_markdown || n.raw_markdown)}</p>`;
    }
    const liveTa = document.getElementById('livePolishedTextarea');
    if (liveTa) {
      liveTa.value = n.polished_markdown || n.raw_markdown || '';
    }

    // View 2: Raw Markdown
    const fnElem = document.getElementById('liveMdFilename');
    if (fnElem) fnElem.innerText = `${n.id}.md`;

    const mdElem = document.getElementById('liveRawMd');
    if (mdElem) mdElem.innerText = n.raw_markdown || '# No markdown extracted yet';

    // View 3: Email Preview
    const subjElem = document.getElementById('mockupSubject');
    if (subjElem) subjElem.innerText = `Subject: [RGU Notice #${n.id}] ${n.title}`;

    const mailBodyElem = document.getElementById('mockupInnerContent');
    if (mailBodyElem) {
      mailBodyElem.innerHTML = `
        <div class="mail-notice-box">
          <div class="mail-badges">
            <span class="m-badge">${escapeHtml(n.category || 'General')}</span>
            <span class="m-badge-id">Notice #${escapeHtml(n.id)}</span>
          </div>
          <h4 class="mail-title-text">${escapeHtml(n.title)}</h4>
          <div class="mail-meta">
            <span>📅 <strong>${escapeHtml(n.published_on || 'Recent')}</strong></span>
            <span><img src="/static/images/logo.png" alt="RGU" style="width: 15px; height: 15px; border-radius: 3px; background: #fff; padding: 1px; vertical-align: middle; margin-right: 4px;"> Raiganj University</span>
          </div>
        </div>
        <div class="gemini-polish-box" style="margin-bottom: 16px; font-size: 12.5px;">
          ${n.polished_html || ''}
        </div>
        <div class="mail-btn-wrap">
          <a href="${escapeHtml(n.link)}" target="_blank" class="mail-fake-btn">📄 View Official Notice &amp; Download PDF</a>
        </div>
      `;
    }

    // Download PDF Button
    const btnFile = document.getElementById('btnLiveDownloadFile');
    if (btnFile) {
      if (data.attachment_url) {
        btnFile.style.display = 'inline-flex';
        btnFile.href = data.attachment_url;
        const lbl = document.getElementById('liveFileBtnLabel');
        if (lbl) lbl.innerText = `Download ${data.attachment_name || 'File'}`;
      } else {
        btnFile.style.display = 'none';
      }
    }
  } catch (err) {
    console.warn('Error loading recent AI notice:', err);
  }
}

function setDashboardPreviewMode(mode) {
  document.getElementById('btnModeAi')?.classList.toggle('active', mode === 'ai');
  document.getElementById('btnModeMd')?.classList.toggle('active', mode === 'md');
  document.getElementById('btnModeEmail')?.classList.toggle('active', mode === 'email');

  const viewAi = document.getElementById('viewAiContent');
  const viewMd = document.getElementById('viewMdContent');
  const viewEmail = document.getElementById('viewEmailContent');

  if (viewAi) viewAi.style.display = mode === 'ai' ? 'block' : 'none';
  if (viewMd) viewMd.style.display = mode === 'md' ? 'block' : 'none';
  if (viewEmail) viewEmail.style.display = mode === 'email' ? 'block' : 'none';
}

function copyLivePolishedText() {
  const ta = document.getElementById('livePolishedTextarea');
  const text = ta ? ta.value : (currentLiveNotice ? (currentLiveNotice.polished_markdown || currentLiveNotice.raw_markdown) : '');
  if (!text) {
    showToast('No polished text available to copy', 'info');
    return;
  }
  navigator.clipboard.writeText(text).then(() => {
    showToast('Gemini polished message copied to clipboard!', 'success');
  }).catch(() => {
    showToast('Failed to copy to clipboard', 'error');
  });
}

function copyLiveMarkdown() {
  const text = document.getElementById('liveRawMd')?.innerText || '';
  navigator.clipboard.writeText(text).then(() => {
    showToast('Markdown (.md) copied to clipboard!', 'success');
  }).catch(() => {
    showToast('Failed to copy to clipboard', 'error');
  });
}

async function regenerateLiveAi() {
  if (!currentLiveNotice) return;
  const btn = document.getElementById('btnLiveRegenAi');
  const origHtml = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Polishing with Gemini...`;
  showToast(`Polishing Notice #${currentLiveNotice.id} with Gemini AI...`, 'info');

  try {
    const res = await fetch(`/api/notices/${currentLiveNotice.id}/generate-polish`, { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      showToast('Gemini AI polish refreshed!', 'success');
      await loadRecentAiNotice();
      await loadLogs();
    } else {
      showToast(data.message || 'Polishing failed', 'error');
    }
  } catch (err) {
    showToast('Polishing error: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = origHtml;
  }
}

function broadcastLiveNotice() {
  if (!currentLiveNotice) return;
  resendNotice(currentLiveNotice.id, currentLiveNotice.title);
}

// ----------------- Notice AI Modal Controller ----------------- //

async function openNoticeAiModal(noticeId) {
  currentModalNoticeId = noticeId;
  openModal('noticeAiModal');

  document.getElementById('modalNoticeAiTitle').innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Loading Notice #${noticeId}...`;
  document.getElementById('modalPolishedHtml').innerHTML = `<div class="loading-placeholder"><i class="fa-solid fa-spinner fa-spin"></i> Extracting Markdown and Gemini Polish...</div>`;
  document.getElementById('modalRawMd').innerText = 'Loading...';

  try {
    const res = await fetch(`/api/notices/${noticeId}/ai-content`);
    const data = await res.json();
    if (!data.success || !data.notice) {
      showToast('Could not load notice AI details', 'error');
      return;
    }

    const n = data.notice;
    document.getElementById('modalNoticeAiTitle').innerHTML = `<i class="fa-solid fa-wand-magic-sparkles header-icon"></i> <span>${escapeHtml(n.title)}</span>`;
    document.getElementById('modalNoticeIdBadge').innerText = `Notice #${n.id}`;
    document.getElementById('modalNoticeCatBadge').innerText = n.category || 'General';
    
    const aiBadge = document.getElementById('modalNoticeAiBadge');
    if (n.has_gemini_polish) {
      aiBadge.className = 'badge badge-success';
      aiBadge.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles"></i> ✨ Gemini Polished`;
    } else {
      aiBadge.className = 'badge badge-info';
      aiBadge.innerHTML = `<i class="fa-solid fa-file-lines"></i> 📝 Markdown Extracted`;
    }

    document.getElementById('modalPolishedHtml').innerHTML = n.polished_html || `<p>${escapeHtml(n.polished_markdown || n.raw_markdown)}</p>`;
    const modalTa = document.getElementById('modalPolishedTextarea');
    if (modalTa) {
      modalTa.value = n.polished_markdown || n.raw_markdown || '';
    }

    document.getElementById('modalMdFilename').innerText = `${n.id}.md`;
    document.getElementById('modalRawMd').innerText = n.raw_markdown || '# No markdown available';
    document.getElementById('modalOfficialPortalLink').href = n.link;

    // Attachment tab
    const attFilename = data.attachment_name;
    if (attFilename) {
      document.getElementById('modalAttFilename').innerText = attFilename;
      document.getElementById('modalAttDownloadLink').href = data.attachment_url;
      document.getElementById('modalAttDownloadLink').style.display = 'inline-flex';
    } else {
      document.getElementById('modalAttFilename').innerText = 'No file attachment captured for this notice';
      document.getElementById('modalAttDownloadLink').style.display = 'none';
    }

    setModalTab('ai');
  } catch (err) {
    showToast('Failed to load AI details: ' + err.message, 'error');
  }
}

function copyModalPolishedText() {
  const ta = document.getElementById('modalPolishedTextarea');
  const text = ta ? ta.value : '';
  if (!text) {
    showToast('No polished text available to copy', 'info');
    return;
  }
  navigator.clipboard.writeText(text).then(() => {
    showToast('Gemini polished announcement copied to clipboard!', 'success');
  }).catch(() => {
    showToast('Failed to copy to clipboard', 'error');
  });
}

function setModalTab(tab) {
  document.getElementById('modalTabAi')?.classList.toggle('active', tab === 'ai');
  document.getElementById('modalTabMd')?.classList.toggle('active', tab === 'md');
  document.getElementById('modalTabAttachment')?.classList.toggle('active', tab === 'att');

  const vAi = document.getElementById('modalViewAi');
  const vMd = document.getElementById('modalViewMd');
  const vAtt = document.getElementById('modalViewAtt');

  if (vAi) vAi.style.display = tab === 'ai' ? 'block' : 'none';
  if (vMd) vMd.style.display = tab === 'md' ? 'block' : 'none';
  if (vAtt) vAtt.style.display = tab === 'att' ? 'block' : 'none';
}

function copyModalMarkdown() {
  const text = document.getElementById('modalRawMd')?.innerText || '';
  navigator.clipboard.writeText(text).then(() => {
    showToast('Markdown (.md) copied to clipboard!', 'success');
  }).catch(() => {
    showToast('Failed to copy to clipboard', 'error');
  });
}

async function regenerateModalAi() {
  if (!currentModalNoticeId) return;
  const btn = document.getElementById('btnModalRegen');
  const origHtml = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Polishing with Gemini...`;

  try {
    const res = await fetch(`/api/notices/${currentModalNoticeId}/generate-polish`, { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      showToast('Gemini AI polish refreshed!', 'success');
      await openNoticeAiModal(currentModalNoticeId);
      await loadRecentAiNotice();
      await loadLogs();
    } else {
      showToast(data.message || 'Polishing failed', 'error');
    }
  } catch (err) {
    showToast('Polishing error: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = origHtml;
  }
}

function dispatchModalNotice() {
  if (!currentModalNoticeId) return;
  const title = document.getElementById('modalNoticeAiTitle')?.innerText || 'Notice';
  resendNotice(currentModalNoticeId, title);
}
