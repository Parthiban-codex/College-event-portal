/* ==============================================================================
   CAMPUS PULSE - STUDENT EVENT PLANNER
   Main Interactive Script: Desk Lamp Mode, Filters, Tactile Interactions
   ============================================================================== */

document.addEventListener('DOMContentLoaded', () => {
    // 1. Desk Lamp Light/Dark Theme Controller
    initDeskLamp();

    // 2. Event Filters & Live Search
    initEventFilters();

    // 3. Auto-dismiss alerts after 5 seconds
    initFlashAlerts();
});

/**
 * Handles toggling and persisting the Desk Lamp (Day / Night Study Mode)
 */
function initDeskLamp() {
    const lampBtn = document.getElementById('deskLampToggle');
    const lampLabel = document.getElementById('deskLampLabel');
    const savedTheme = localStorage.getItem('campus_desk_theme') || 'light';

    // Apply saved theme immediately
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateLampUI(savedTheme);

    if (lampBtn) {
        lampBtn.addEventListener('click', () => {
            const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
            const nextTheme = currentTheme === 'light' ? 'dark' : 'light';
            
            document.documentElement.setAttribute('data-theme', nextTheme);
            localStorage.setItem('campus_desk_theme', nextTheme);
            updateLampUI(nextTheme);

            // Play subtle click sensation
            playDeskClick();
        });
    }

    function updateLampUI(theme) {
        if (!lampLabel) return;
        if (theme === 'dark') {
            lampLabel.textContent = 'Night Kraft';
        } else {
            lampLabel.textContent = 'Day Paper';
        }
    }
}

/**
 * Filter event cards on the desk catalog by category chips and live search
 */
function initEventFilters() {
    const searchInput = document.getElementById('eventSearchInput');
    const chips = document.querySelectorAll('.filter-chip');
    const cards = document.querySelectorAll('.event-index-card');

    let activeCategory = 'all';

    chips.forEach(chip => {
        chip.addEventListener('click', () => {
            chips.forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
            activeCategory = chip.getAttribute('data-category') || 'all';
            filterCards();
        });
    });

    if (searchInput) {
        searchInput.addEventListener('input', () => {
            filterCards();
        });
    }

    function filterCards() {
        const query = searchInput ? searchInput.value.toLowerCase().trim() : '';

        cards.forEach(card => {
            const title = (card.getAttribute('data-title') || '').toLowerCase();
            const category = card.getAttribute('data-category') || '';
            const matchCategory = (activeCategory === 'all' || category === activeCategory);
            const matchQuery = (query === '' || title.includes(query));

            if (matchCategory && matchQuery) {
                card.style.display = 'flex';
            } else {
                card.style.display = 'none';
            }
        });
    }
}

/**
 * Auto fade out flash messages
 */
function initFlashAlerts() {
    const alerts = document.querySelectorAll('.flash-alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
            alert.style.opacity = '0';
            alert.style.transform = 'translateY(-10px)';
            setTimeout(() => alert.remove(), 400);
        }, 5000);
    });
}

/**
 * Play subtle tactile desk click audio using Web Audio API (no external asset needed)
 */
function playDeskClick() {
    try {
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        if (!AudioContext) return;
        const ctx = new AudioContext();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();

        osc.type = 'sine';
        osc.frequency.setValueAtTime(800, ctx.currentTime);
        osc.frequency.exponentialRampToValueAtTime(300, ctx.currentTime + 0.04);

        gain.gain.setValueAtTime(0.12, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.04);

        osc.connect(gain);
        gain.connect(ctx.destination);

        osc.start();
        osc.stop(ctx.currentTime + 0.04);
    } catch (e) {
        // AudioContext disabled or blocked; silent fallback
    }
}

/**
 * Print Admit-One Pass
 */
function printTicketPass() {
    window.print();
}
