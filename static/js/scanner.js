// QR Code Gate Attendance Scanner for Event Organizers

let html5QrCode = null;
let isScanning = false;
let audioCtx = null;

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

    if (!ticketCode || !resultBox) return;

    resultBox.innerHTML = `
        <div style="padding: 1.5rem; text-align: center; border: 1.5px dashed var(--card-border); border-radius: 8px;">
            <p style="font-weight: 700; color: var(--ink-pen-blue);">🔍 Verifying Ticket Code: <code>${ticketCode}</code>...</p>
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
            resultBox.innerHTML = `
                <div style="background: var(--sticky-mint); border: 2px solid var(--stamp-green); border-radius: 8px; padding: 1.5rem; text-align: left;">
                    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 1rem;">
                        <span class="rubber-stamp stamp-verified">✓ ATTENDANCE RECORDED</span>
                        <small style="color: var(--ink-pencil); font-family: var(--font-mono);">${data.timestamp}</small>
                    </div>
                    <div style="background: var(--paper-card); padding: 1rem; border-radius: 6px; border: 1px solid var(--card-border);">
                        <p style="margin-bottom: 0.3rem;"><strong>Student:</strong> ${data.student.name} (<span style="font-family: var(--font-mono); color: var(--ink-pen-blue);">${data.student.roll_number}</span>)</p>
                        <p style="margin-bottom: 0.3rem;"><strong>Department:</strong> ${data.student.department}</p>
                        <p style="margin-bottom: 0.3rem;"><strong>Event:</strong> ${data.student.event}</p>
                        <p style="margin: 0;"><strong>Ticket Pass:</strong> <code style="font-family: var(--font-mono); font-weight: 700;">${data.student.ticket_code}</code></p>
                    </div>
                </div>
            `;
        } else if (data.already_attended) {
            playBeep('error');
            resultBox.innerHTML = `
                <div style="background: var(--sticky-yellow); border: 2px solid var(--stamp-orange); border-radius: 8px; padding: 1.5rem; text-align: left;">
                    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.8rem;">
                        <span class="rubber-stamp stamp-pending">⚠️ ALREADY CHECKED IN</span>
                    </div>
                    <p style="font-weight: 700; margin-bottom: 0.4rem;">${data.message}</p>
                    <p style="margin: 0;">Student: <strong>${data.student.name}</strong> (${data.student.roll_number})</p>
                </div>
            `;
        } else {
            playBeep('error');
            resultBox.innerHTML = `
                <div style="background: var(--sticky-rose); border: 2px solid var(--stamp-red); border-radius: 8px; padding: 1.5rem; text-align: left;">
                    <div style="margin-bottom: 0.5rem;">
                        <span class="rubber-stamp stamp-rejected">❌ CHECK-IN REJECTED</span>
                    </div>
                    <p style="font-weight: 700; margin: 0; color: #991b1b;">${data.message}</p>
                </div>
            `;
        }
    } catch (err) {
        playBeep('error');
        resultBox.innerHTML = `
            <div class="flash-alert alert-danger">
                Error connecting to check-in server. Please verify connection.
            </div>
        `;
    }
}

function startCameraScanner() {
    const startBtn = document.getElementById('btn-start-scanner');
    const stopBtn = document.getElementById('btn-stop-scanner');

    if (!html5QrCode && window.Html5Qrcode) {
        html5QrCode = new Html5Qrcode("qr-reader");
    } else if (!window.Html5Qrcode) {
        alert('QR Camera library loading. Please try again in a moment or use manual code entry.');
        return;
    }

    const config = { fps: 10, qrbox: { width: 220, height: 220 } };

    html5QrCode.start(
        { facingMode: "environment" },
        config,
        (decodedText) => {
            processTicketScan(decodedText);
        },
        () => {}
    ).then(() => {
        isScanning = true;
        if (startBtn) startBtn.style.display = 'none';
        if (stopBtn) stopBtn.style.display = 'inline-flex';
    }).catch(err => {
        console.error('Camera scan error:', err);
        alert('Could not start camera. Please ensure camera permissions are granted or use manual ticket code entry.');
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
        }).catch(err => console.error(err));
    }
}

function handleQrFileUpload(input) {
    if (!input.files || input.files.length === 0) return;
    const file = input.files[0];

    if (!html5QrCode && window.Html5Qrcode) {
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
