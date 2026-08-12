// Gate authentication: continuously scans the webcam and sends captured frames
// to the backend for facial comparison against stored passenger faces.

let gateStream = null;
let gateScanning = false;
let gateTimer = null;

function startGateScan() {
  const video = document.getElementById('gateVideo');
  const canvas = document.getElementById('gateCanvas');
  const startBtn = document.getElementById('gateStartBtn');
  const stopBtn = document.getElementById('gateStopBtn');

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    alert('Webcam not supported by this browser.');
    return;
  }

  navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } })
    .then(function(stream) {
      gateStream = stream;
      video.srcObject = stream;
      video.play();
      gateScanning = true;
      startBtn.style.display = 'none';
      stopBtn.style.display = 'inline-flex';
      stopBtn.disabled = false;
      hideGateResult();
      showGateStatus('Looking at the camera...');
      scanLoop();
    })
    .catch(function(err) {
      alert('Unable to access webcam: ' + err.message);
    });
}

function stopGateScan() {
  gateScanning = false;
  if (gateTimer) { clearTimeout(gateTimer); gateTimer = null; }
  if (gateStream) {
    gateStream.getTracks().forEach(function(t) { t.stop(); });
    gateStream = null;
  }
  const video = document.getElementById('gateVideo');
  if (video) video.srcObject = null;
  document.getElementById('gateStartBtn').style.display = 'inline-flex';
  document.getElementById('gateStopBtn').style.display = 'none';
  hideGateStatus();
}

function scanLoop() {
  if (!gateScanning) return;
  const video = document.getElementById('gateVideo');
  const canvas = document.getElementById('gateCanvas');
  const ctx = canvas.getContext('2d');
  canvas.width = 320;
  canvas.height = 320;
  ctx.save();
  ctx.scale(-1, 1);
  ctx.drawImage(video, -320, 0, 320, 320);
  ctx.restore();
  const dataUrl = canvas.toDataURL('image/jpeg', 0.8);

  showGateStatus('Checking your ticket...');

  fetch('/api/gate/verify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image: dataUrl })
  })
    .then(function(r) { return r.json(); })
    .then(function(data) { handleGateResult(data); })
    .catch(function(err) {
      showGateStatus('Having trouble connecting. Please wait...');
    });

  gateTimer = setTimeout(scanLoop, 4000);
}

function handleGateResult(data) {
  const result = document.getElementById('gateResult');
  const status = data.status;
  hideGateStatus();

  if (status === 'Authorized') {
    result.className = 'gate-result result-authorized show';
    result.innerHTML =
      '<div class="result-icon"><i class="ph-fill ph-check-circle" style="color:var(--green);"></i></div>' +
      '<div class="result-title" style="color:var(--green-text);">Welcome!</div>' +
      '<div class="result-detail"><strong>' + escapeHtml(data.passenger_name || '') + '</strong> &mdash; ' +
      escapeHtml(data.booking_id || '') + '</div>' +
      '<p class="text-muted small mt-2 mb-0">Entry recorded. Gate opening...</p>';
  } else if (status === 'Already Used') {
    result.className = 'gate-result result-used show';
    result.innerHTML =
      '<div class="result-icon"><i class="ph-fill ph-warning-circle" style="color:var(--amber);"></i></div>' +
      '<div class="result-title" style="color:var(--amber-text);">Already Used</div>' +
      '<div class="result-detail"><strong>' + escapeHtml(data.passenger_name || '') + '</strong> &mdash; ' +
      escapeHtml(data.booking_id || '') + '</div>' +
      '<p class="text-muted small mt-2 mb-0">This ticket has already been scanned.</p>';
  } else if (status === 'Expired') {
    result.className = 'gate-result result-expired show';
    result.innerHTML =
      '<div class="result-icon"><i class="ph-fill ph-clock-countdown" style="color:var(--text-muted);"></i></div>' +
      '<div class="result-title" style="color:var(--text-secondary);">Ticket Expired</div>' +
      '<div class="result-detail">' +
      (data.passenger_name ? '<strong>' + escapeHtml(data.passenger_name) + '</strong> &mdash; ' : '') +
      escapeHtml(data.booking_id || '') + '</div>' +
      '<p class="text-muted small mt-2 mb-0">This ticket is no longer valid.</p>';
  } else {
    result.className = 'gate-result result-unauthorized show';
    result.innerHTML =
      '<div class="result-icon"><i class="ph-fill ph-x-circle" style="color:var(--red);"></i></div>' +
      '<div class="result-title" style="color:var(--red-text);">Access Denied</div>' +
      '<p class="result-detail mb-0">No matching ticket found. Please try again or use Backup Entry below.</p>';
  }

  // Auto-hide result after 6 seconds if scanning
  if (gateScanning) {
    setTimeout(function() {
      if (gateScanning) hideGateResult();
    }, 6000);
  }
}

function hideGateResult() {
  document.getElementById('gateResult').className = 'gate-result';
}
function showGateStatus(msg) {
  const el = document.getElementById('gateStatus');
  el.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span> ' + escapeHtml(msg);
  el.classList.add('show');
  hideGateResult();
}
function hideGateStatus() {
  const el = document.getElementById('gateStatus');
  el.classList.remove('show');
  el.innerHTML = '';
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, function(c) {
    return { '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c];
  });
}

// ---------------------------------------------------------------------------
// Backup Authentication (Booking Reference ID Manual Lookup & Entry)
// ---------------------------------------------------------------------------

function handleManualLookup() {
  const input = document.getElementById('manualBookingIdInput');
  const container = document.getElementById('manualDetailsContainer');
  const btn = document.getElementById('manualLookupBtn');

  const bookingId = (input ? input.value : '').trim();
  if (!bookingId) return;

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Searching...';
  container.style.display = 'block';
  container.innerHTML = '<div class="text-center py-3 text-muted"><span class="spinner-border spinner-border-sm me-2"></span>Looking up your booking...</div>';

  fetch('/api/gate/lookup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ booking_id: bookingId })
  })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      btn.disabled = false;
      btn.innerHTML = '<i class="ph ph-magnifying-glass"></i> Look Up';
      renderManualLookupResult(data);
    })
    .catch(function(err) {
      btn.disabled = false;
      btn.innerHTML = '<i class="ph ph-magnifying-glass"></i> Look Up';
      container.innerHTML = '<div class="alert alert-danger mb-0 py-2 small">Connection error. Please try again.</div>';
    });
}

function renderManualLookupResult(data) {
  const container = document.getElementById('manualDetailsContainer');
  container.style.display = 'block';

  if (data.status === 'NotFound') {
    container.innerHTML =
      '<div class="d-flex align-items-center gap-2 p-3" style="background:var(--red-bg);border:1px solid var(--red-border);border-radius:var(--radius-md);">' +
        '<i class="ph ph-warning-circle text-red" style="font-size:1.3rem;"></i>' +
        '<div class="small"><strong>Not Found</strong> &mdash; ' + escapeHtml(data.message) + '</div>' +
      '</div>';
    return;
  }

  const b = data.booking || {};
  const passengers = data.passengers || [];
  const statusClass = 'status-' + (b.status || '').toLowerCase();

  let html =
    '<div class="p-3 mt-2" style="background:var(--bg-subtle);border:1px solid var(--border);border-radius:var(--radius-md);">' +
      '<div class="d-flex justify-content-between align-items-center flex-wrap gap-2 mb-3 pb-2" style="border-bottom:1px solid var(--border);">' +
        '<div>' +
          '<div class="text-muted small">Booking Reference</div>' +
          '<h5 class="fw-bold text-brand mb-0">' + escapeHtml(b.booking_id || '') + '</h5>' +
        '</div>' +
        '<div><span class="status-badge ' + statusClass + '">' + escapeHtml(b.status || '') + '</span></div>' +
      '</div>' +

      '<div class="row g-2 mb-3 small">' +
        '<div class="col-6 col-md-3">' +
          '<div class="text-muted">Route</div>' +
          '<div class="fw-semibold">' + escapeHtml(b.source || '') + ' &rarr; ' + escapeHtml(b.destination || '') + '</div>' +
        '</div>' +
        '<div class="col-6 col-md-3">' +
          '<div class="text-muted">Travel Date</div>' +
          '<div class="fw-semibold">' + escapeHtml(b.travel_date || '') + '</div>' +
        '</div>' +
        '<div class="col-6 col-md-3">' +
          '<div class="text-muted">Passengers</div>' +
          '<div class="fw-semibold">' + (b.passenger_count || passengers.length) + ' Person(s)</div>' +
        '</div>' +
        '<div class="col-6 col-md-3">' +
          '<div class="text-muted">Total Fare</div>' +
          '<div class="fw-semibold text-green">' + (b.fare ? '&#8377;' + Math.round(b.fare) : 'N/A') + '</div>' +
        '</div>' +
      '</div>' +

      '<h6 class="fw-bold mb-2 small text-uppercase text-muted" style="letter-spacing:0.5px;">Passengers</h6>' +
      '<div class="table-responsive mb-3">' +
        '<table class="table table-sm table-bordered align-middle bg-white mb-0 small">' +
          '<thead class="table-light">' +
            '<tr><th>#</th><th>Name</th><th>Age</th><th>Gender</th><th>Status</th><th>Action</th></tr>' +
          '</thead>' +
          '<tbody>';

  passengers.forEach(function(p, idx) {
    const pStatusClass = 'status-' + (p.ticket_status || '').toLowerCase();
    const isActive = p.ticket_status === 'Active' && b.status === 'Active';

    html +=
      '<tr>' +
        '<td>' + (idx + 1) + '</td>' +
        '<td class="fw-semibold">' + escapeHtml(p.name || '') + '</td>' +
        '<td>' + p.age + '</td>' +
        '<td>' + escapeHtml(p.gender || '') + '</td>' +
        '<td><span class="status-badge ' + pStatusClass + '">' + escapeHtml(p.ticket_status || '') + '</span></td>' +
        '<td>';

    if (isActive) {
      html +=
        '<button type="button" class="btn btn-sm btn-success py-1 px-2 fw-semibold" ' +
        'onclick="manualAuthorizeEntry(\'' + escapeHtml(b.booking_id) + '\', ' + p.id + ', this)">' +
          '<i class="ph ph-check-circle me-1"></i> Allow Entry' +
        '</button>';
    } else if (p.ticket_status === 'Entered') {
      html += '<span class="text-muted small"><i class="ph ph-check text-green"></i> Entered</span>';
    } else {
      html += '<span class="text-muted small">' + escapeHtml(p.ticket_status) + '</span>';
    }

    html += '</td></tr>';
  });

  html += '</tbody></table></div>';

  const activePassengers = passengers.filter(function(p) { return p.ticket_status === 'Active'; });
  if (activePassengers.length > 1 && b.status === 'Active') {
    html +=
      '<div class="text-end">' +
        '<button type="button" class="btn-brand btn-sm px-3" ' +
        'onclick="manualAuthorizeEntry(\'' + escapeHtml(b.booking_id) + '\', null, this)">' +
          '<i class="ph ph-door-open me-1"></i> Allow Entry (Next Person)' +
        '</button>' +
      '</div>';
  }

  html += '</div>';
  container.innerHTML = html;
}

function manualAuthorizeEntry(bookingId, passengerId, btnElem) {
  if (btnElem) {
    btnElem.disabled = true;
    btnElem.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Processing...';
  }

  fetch('/api/gate/manual-authorize', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ booking_id: bookingId, passenger_id: passengerId })
  })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      handleGateResult(data);
      window.scrollTo({ top: 0, behavior: 'smooth' });
      handleManualLookup();
    })
    .catch(function(err) {
      if (btnElem) {
        btnElem.disabled = false;
        btnElem.innerHTML = '<i class="ph ph-arrow-counter-clockwise me-1"></i> Try Again';
      }
      alert('Connection error. Please try again.');
    });
}
