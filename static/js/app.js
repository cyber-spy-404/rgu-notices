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

document.addEventListener('DOMContentLoaded', () => {
  initApp();
});

async function initApp() {
  await fetchSystemStatus();
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
  document.querySelectorAll('.nav-tab').forEach(t => {
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
    document.getElementById('metricCapturedEmails').innerText = data.stats.captured_emails || 0;

    // Badges in header
    document.getElementById('navStudentCount').innerText = data.stats.total_students || 0;
    document.getElementById('navNoticeCount').innerText = data.stats.total_notices || 0;

    // SMTP Badge
    const smtpBadgeText = document.getElementById('smtpBadgeText');
    if (data.smtp_mode === 'local') {
      const isRunning = data.smtp_server.running;
      smtpBadgeText.innerText = `SMTP: Local (${data.smtp_server.port}) ${isRunning ? 'Active' : 'Offline'}`;
    } else {
      smtpBadgeText.innerText = `SMTP: Custom (${data.sender_email || 'Configured'})`;
    }

    // Dashboard info card
    document.getElementById('dashLastRun').innerText = data.stats.last_scraped_at || 'Never executed yet';
    document.getElementById('dashNextRun').innerText = data.scheduler.next_run || 'Tomorrow at 00:00:00';
    document.getElementById('dashSmtpChannel').innerText = data.smtp_mode === 'local' 
      ? `Built-in Local SMTP Server (${data.smtp_server.host}:${data.smtp_server.port})` 
      : `Custom SMTP Server`;
    document.getElementById('dashStudentAudience').innerText = `${data.stats.active_students} active enrolled student(s)`;
    document.getElementById('metricNextRunText').innerText = `Next run: ${data.scheduler.next_run || '00:00:00'}`;

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
      // Reached 00:00:00! Trigger status refresh
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
      showToast(`Scan complete: No new notices found. Total tracked: ${data.total_scraped}. Rescheduled for 00:00.`, 'info');
    } else {
      showToast(data.message || 'Scrape completed with notice check.', 'info');
    }

    await fetchSystemStatus();
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
          <span style="margin-left: 8px; font-size: 12px; color: ${s.is_active ? 'var(--accent-emerald)' : 'var(--text-subtle)'};">
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

  tbody.innerHTML = notices.map(n => {
    return `
      <tr>
        <td><span class="badge badge-info" style="font-family: var(--font-mono);">${escapeHtml(n.id)}</span></td>
        <td>
          <a href="${escapeHtml(n.link)}" target="_blank" class="accent-link" style="font-weight: 600;">
            ${escapeHtml(n.title)}
          </a>
        </td>
        <td><span class="badge badge-neutral">${escapeHtml(n.category || 'General')}</span></td>
        <td style="font-size: 12.5px; color: var(--text-muted);">${escapeHtml(n.published_on || '—')}</td>
        <td>
          <span class="badge ${n.email_status === 'sent' ? 'badge-success' : 'badge-warning'}">
            <i class="fa-solid ${n.email_status === 'sent' ? 'fa-check' : 'fa-clock'}"></i>
            ${n.email_status === 'sent' ? 'Emailed' : 'Pending/Logged'}
          </span>
        </td>
        <td>
          <div style="display: flex; gap: 6px;">
            <a href="${escapeHtml(n.link)}" target="_blank" class="btn btn-icon" title="Open on Raiganj University Portal">
              <i class="fa-solid fa-arrow-up-right-from-square"></i>
            </a>
            <button class="btn btn-icon" title="Email this notice to all students right now" onclick="resendNotice('${n.id}', '${escapeHtml(n.title)}')">
              <i class="fa-solid fa-paper-plane"></i>
            </button>
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
      <td><span class="badge badge-info" style="font-family: var(--font-mono);">${escapeHtml(n.id)}</span></td>
      <td>
        <a href="${escapeHtml(n.link)}" target="_blank" class="accent-link" style="font-weight: 500;">
          ${escapeHtml(n.title)}
        </a>
      </td>
      <td><span class="badge badge-neutral">${escapeHtml(n.category || 'General')}</span></td>
      <td style="font-size: 12px; color: var(--text-muted);">${escapeHtml(n.published_on || '—')}</td>
      <td>
        <button class="btn btn-secondary btn-xs" onclick="resendNotice('${n.id}', '${escapeHtml(n.title)}')">
          <i class="fa-solid fa-paper-plane"></i> Send
        </button>
      </td>
    </tr>
  `).join('');
}

function filterNoticeCat(cat) {
  currentCategoryFilter = cat;
  document.querySelectorAll('#noticeCategoryFilters .filter-pill').forEach(p => {
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

// ----------------- SMTP Settings & Mailbox ----------------- //
async function loadSmtpConfig() {
  try {
    const res = await fetch('/api/smtp/config');
    const cfg = await res.json();

    document.getElementById('smtpSenderEmail').value = cfg.sender_email || '';
    document.getElementById('smtpSenderName').value = cfg.sender_name || '';
    document.getElementById('smtpLocalHost').value = cfg.local_host || '127.0.0.1';
    document.getElementById('smtpLocalPort').value = cfg.local_port || 1025;
    document.getElementById('smtpCustomHost').value = cfg.custom_host || '';
    document.getElementById('smtpCustomPort').value = cfg.custom_port || 587;
    document.getElementById('smtpCustomUser').value = cfg.custom_username || '';
    document.getElementById('smtpCustomPass').value = cfg.custom_password_masked || '';
    document.getElementById('smtpCustomTls').checked = !!cfg.custom_use_tls;
    document.getElementById('smtpCustomSsl').checked = !!cfg.custom_use_ssl;

    const modeRadio = document.querySelector(`input[name="smtp_mode"][value="${cfg.mode || 'local'}"]`);
    if (modeRadio) modeRadio.checked = true;

    toggleSmtpModeFields();
    document.getElementById('currentSmtpModeBadge').innerText = `Mode: ${cfg.mode === 'local' ? 'Built-in Local SMTP' : 'Custom SMTP'}`;
  } catch (err) {
    console.error('Error loading SMTP config:', err);
  }
}

function toggleSmtpModeFields() {
  const selectedMode = document.querySelector('input[name="smtp_mode"]:checked')?.value || 'local';
  document.getElementById('localSmtpFields').style.display = selectedMode === 'local' ? 'block' : 'none';
  document.getElementById('customSmtpFields').style.display = selectedMode === 'custom' ? 'block' : 'none';
}

async function saveSmtpConfig(e) {
  e.preventDefault();
  const selectedMode = document.querySelector('input[name="smtp_mode"]:checked').value;

  const payload = {
    mode: selectedMode,
    sender_email: document.getElementById('smtpSenderEmail').value.trim(),
    sender_name: document.getElementById('smtpSenderName').value.trim(),
    local_host: document.getElementById('smtpLocalHost').value.trim(),
    local_port: parseInt(document.getElementById('smtpLocalPort').value),
    custom_host: document.getElementById('smtpCustomHost').value.trim(),
    custom_port: parseInt(document.getElementById('smtpCustomPort').value),
    custom_username: document.getElementById('smtpCustomUser').value.trim(),
    custom_password: document.getElementById('smtpCustomPass').value.trim(),
    custom_use_tls: document.getElementById('smtpCustomTls').checked ? 1 : 0,
    custom_use_ssl: document.getElementById('smtpCustomSsl').checked ? 1 : 0
  };

  try {
    const res = await fetch('/api/smtp/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.success) {
      showToast('SMTP settings updated successfully!', 'success');
      loadSmtpConfig();
      fetchSystemStatus();
    }
  } catch (err) {
    showToast('Failed to save SMTP settings: ' + err.message, 'error');
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
      <td style="font-weight: 500; color: #fff;">${escapeHtml(m.subject || '(No Subject)')}</td>
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

// ----------------- SMTP Test Modal ----------------- //
function openTestModal() {
  document.getElementById('testResultBox').style.display = 'none';
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
    consoleElem.innerHTML = `<div class="log-line" style="color: var(--text-subtle);">No execution logs recorded yet.</div>`;
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
  document.querySelectorAll('#logLevelFilters .filter-pill').forEach(p => {
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
  if (e.target.classList.contains('modal-overlay')) {
    e.target.classList.remove('active');
  }
});

// ----------------- Toast Notifications ----------------- //
function showToast(message, type = 'info') {
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;

  const icon = type === 'success' ? 'fa-circle-check' : (type === 'error' ? 'fa-circle-xmark' : 'fa-circle-info');
  toast.innerHTML = `
    <i class="fa-solid ${icon}"></i>
    <span>${escapeHtml(message)}</span>
  `;

  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(100%)';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
