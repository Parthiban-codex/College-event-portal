// QR Code Gate Attendance Scanner for Event Organizers

let html5QrCode = null;
let isScanning = false;
let scannerStarting = false;
let scanInProgress = false;
let lastScannedCode = '';
let lastScanTime = 0;
let audioCtx = null;

function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, character => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
    })[character]);
}

function setScannerStatus(message) {
    const status = document.getElementById('scanner-status');
    if (status) status.textContent = message;
}

function playBeep(type = 'success') {
    try {
        if (!audioCtx) {
            audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        }
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.connect(gain);
        gain.connect(audioCtx.destination);

        if (type === 'success') {
            osc.frequency.setValueAtTime(587.33, audioCtx.currentTime);
            osc.frequency.setValueAtTime(880, audioCtx.currentTime + 0.1);
            gain.gain.setValueAtTime(0.25, audioCtx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.3);
            osc.start();
            osc.stop(audioCtx.currentTime + 0.3);
        } else {
            osc.frequency.setValueAtTime(220, audioCtx.currentTime);
            osc.frequency.setValueAtTime(160, audioCtx.currentTime + 0.15);
            gain.gain.setValueAtTime(0.3, audioCtx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.35);
            osc.start();
            osc.stop(audioCtx.currentTime + 0.35);
        }
    } catch (e) {}
}

async function processTicketScan(ticketCode) {
    const resultBox = document.getElementById('scan-result-container');
    const eventSelect = document.getElementById('scanner-event-filter');
    const selectedEventId = eventSelect ? eventSelect.value : null;

    if (!ticketCode || !resultBox || scanInProgress) return;
    const now = Date.now();
    if (ticketCode === lastScannedCode && now - lastScanTime < 2500) return;
    scanInProgress = true;
    lastScannedCode = ticketCode;
    lastScanTime = now;
    setScannerStatus('QR detected. Verifying ticket…');

    resultBox.innerHTML = `
        <div style="padding: 1.5rem; text-align: center; border: 1.5px dashed var(--card-border); border-radius: 8px;">
            <p style="font-weight: 700; color: var(--ink-pen-blue);">🔍 Verifying Ticket Code: <code>${escapeHtml(ticketCode)}</code>...</p>
        </div>
    `;

    try {
        const res = await fetch('/api/scan-ticket', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ticket_code: ticketCode,
                event_id: selectedEventId || null
            })
        });

        const data = await res.json();

        if (data.success) {
            playBeep('success');
            setScannerStatus('Pass checked in. Show the next ticket QR code to continue.');
            resultBox.innerHTML = `
                <div style="background: var(--sticky-mint); border: 2px solid var(--stamp-green); border-radius: 8px; padding: 1.5rem; text-align: left;">
                    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 1rem;">
                        <span class="rubber-stamp stamp-verified">✓ ATTENDANCE RECORDED</span>
                        <small style="color: var(--ink-pencil); font-family: var(--font-mono);">${escapeHtml(data.timestamp)}</small>
                    </div>
                    <div style="background: var(--paper-card); padding: 1rem; border-radius: 6px; border: 1px solid var(--card-border);">
                        <p style="margin-bottom: 0.3rem;"><strong>Student:</strong> ${escapeHtml(data.student.name)} (<span style="font-family: var(--font-mono); color: var(--ink-pen-blue);">${escapeHtml(data.student.roll_number)}</span>)</p>
                        <p style="margin-bottom: 0.3rem;"><strong>Department:</strong> ${escapeHtml(data.student.department)}</p>
                        <p style="margin-bottom: 0.3rem;"><strong>Event:</strong> ${escapeHtml(data.student.event)}</p>
                        <p style="margin: 0;"><strong>Ticket Pass:</strong> <code style="font-family: var(--font-mono); font-weight: 700;">${escapeHtml(data.student.ticket_code)}</code></p>
                    </div>
                </div>
            `;
        } else if (data.already_attended) {
            playBeep('error');
            setScannerStatus('This ticket was already checked in.');
            resultBox.innerHTML = `
                <div style="background: var(--sticky-yellow); border: 2px solid var(--stamp-orange); border-radius: 8px; padding: 1.5rem; text-align: left;">
                    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.8rem;">
                        <span class="rubber-stamp stamp-pending">⚠️ ALREADY CHECKED IN</span>
                    </div>
                    <p style="font-weight: 700; margin-bottom: 0.4rem;">${escapeHtml(data.message)}</p>
                    <p style="margin: 0;">Student: <strong>${escapeHtml(data.student.name)}</strong> (${escapeHtml(data.student.roll_number)})</p>
                </div>
            `;
        } else {
            playBeep('error');
            setScannerStatus(data.message || 'This ticket could not be verified.');
            resultBox.innerHTML = `
                <div style="background: var(--sticky-rose); border: 2px solid var(--stamp-red); border-radius: 8px; padding: 1.5rem; text-align: left;">
                    <div style="margin-bottom: 0.5rem;">
                        <span class="rubber-stamp stamp-rejected">❌ CHECK-IN REJECTED</span>
                    </div>
                    <p style="font-weight: 700; margin: 0; color: #991b1b;">${escapeHtml(data.message || 'This ticket could not be verified.')}</p>
                </div>
            `;
        }
    } catch (err) {
        playBeep('error');
        setScannerStatus('Could not connect to the check-in server. Check your connection and try again.');
        resultBox.innerHTML = `
            <div class="flash-alert alert-danger">
                Error connecting to check-in server. Please verify connection.
            </div>
        `;
        console.error('Ticket verification error:', err);
    } finally {
        scanInProgress = false;
    }
}

function startCameraScanner() {
    const startBtn = document.getElementById('btn-start-scanner');
    const stopBtn = document.getElementById('btn-stop-scanner');

    if (scannerStarting || isScanning || html5QrCode && html5QrCode.isScanning) return;
    if (!html5QrCode && window.Html5Qrcode) {
        html5QrCode = new Html5Qrcode("qr-reader");
    } else if (!window.Html5Qrcode) {
        setScannerStatus('The QR scanner library did not load. Refresh the page or enter the ticket code manually.');
        return;
    }
    if (!window.isSecureContext) {
        setScannerStatus('Camera access requires HTTPS (or localhost). Open this page securely or enter the ticket code manually.');
        return;
    }

    const config = { fps: 10, qrbox: { width: 220, height: 220 } };

    scannerStarting = true;
    html5QrCode.start(
        { facingMode: "environment" },
        config,
        (decodedText) => {
            processTicketScan(decodedText.trim());
        },
        () => {}
    ).then(() => {
        scannerStarting = false;
        isScanning = true;
        if (startBtn) startBtn.style.display = 'none';
        if (stopBtn) stopBtn.style.display = 'inline-flex';
        setScannerStatus('Camera ready. Center a ticket QR code in the frame.');
    }).catch(err => {
        scannerStarting = false;
        isScanning = false;
        console.error('Camera scan error:', err);
        setScannerStatus('Could not start the camera. Allow camera permission and use HTTPS, or enter the ticket code manually.');
    });
}

function stopCameraScanner() {
    const startBtn = document.getElementById('btn-start-scanner');
    const stopBtn = document.getElementById('btn-stop-scanner');

    if (html5QrCode && isScanning) {
        html5QrCode.stop().then(() => {
            isScanning = false;
            if (startBtn) startBtn.style.display = 'inline-flex';
            if (stopBtn) stopBtn.style.display = 'none';
            setScannerStatus('Camera stopped. Start it again or enter a ticket code manually.');
        }).catch(err => {
            setScannerStatus('Could not stop the camera cleanly. Refresh the page if it remains active.');
            console.error('Camera shutdown error:', err);
        });
    }
}

function handleQrFileUpload(input) {
    if (!input.files || input.files.length === 0) return;
    const file = input.files[0];

    if (!window.Html5Qrcode) {
        setScannerStatus('The QR scanner library did not load. Refresh the page or enter the ticket code manually.');
        return;
    }

    if (!html5QrCode) {
        html5QrCode = new Html5Qrcode("qr-reader");
    }

    html5QrCode.scanFile(file, true)
        .then(decodedText => {
            processTicketScan(decodedText);
        })
        .catch(() => {
            alert('No valid QR ticket detected in this image. Please upload a clear ticket pass image or enter code manually.');
        });
}

document.addEventListener('DOMContentLoaded', () => {
    const manualForm = document.getElementById('manual-ticket-form');
    if (manualForm) {
        manualForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const input = document.getElementById('manual-ticket-code');
            if (input && input.value.trim()) {
                processTicketScan(input.value.trim());
            }
        });
    }
});
