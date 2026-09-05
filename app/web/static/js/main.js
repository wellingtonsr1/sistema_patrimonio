// SisPatrimônio Pro — Main JavaScript
document.addEventListener('DOMContentLoaded', () => {
    // ============================================================
    // Bootstrap Tooltips
    // ============================================================
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(el => new bootstrap.Tooltip(el));

    // Auto-dismiss alerts
    document.querySelectorAll('.alert-dismissible').forEach(alert => {
        setTimeout(() => {
            try { new bootstrap.Alert(alert).close(); } catch(e) {}
        }, 5000);
    });

    // ============================================================
    // Dark Mode
    // ============================================================
    initDarkMode();

    // ============================================================
    // Animated Counters on KPI cards
    // ============================================================
    animateCounters();
});

// ================================================================
// DARK MODE
// ================================================================
function initDarkMode() {
    const saved = localStorage.getItem('sispatrim-theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const theme = saved || (prefersDark ? 'dark' : 'light');
    applyTheme(theme);
}

function toggleDarkMode() {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    applyTheme(next);
    localStorage.setItem('sispatrim-theme', next);
}

function applyTheme(theme) {
    // Sincroniza o atributo do Bootstrap (data-bs-theme) com o tema da aplicação
    // para que componentes/utilitários do Bootstrap (text-muted, alerts, dropdowns,
    // modais, accordion, placeholders, etc.) sigam o mesmo tema.
    document.documentElement.setAttribute('data-theme', theme);
    document.documentElement.setAttribute('data-bs-theme', theme);
    const icon = document.getElementById('darkIcon');
    if (icon) {
        icon.className = theme === 'dark' ? 'bi bi-sun-fill' : 'bi bi-moon-stars';
    }
    // Notifica componentes (ex.: gráficos) para se reajustarem ao novo tema
    document.dispatchEvent(new CustomEvent('sispatrim-theme-change', { detail: { theme } }));
}

// ================================================================
// MOBILE SIDEBAR
// ================================================================
function showSidebarOnMobile() {
    const sidebar = document.getElementById('mobileSidebar');
    if (sidebar && window.innerWidth < 1200) {
        sidebar.style.display = 'flex';
    }
}

function openSidebar() {
    const sidebar = document.getElementById('mobileSidebar');
    if (!sidebar) return;
    sidebar.style.display = 'flex';
    sidebar.classList.add('active');
    document.getElementById('sidebarOverlay').classList.add('active');
    document.body.style.overflow = 'hidden';
}

function closeSidebar() {
    const sidebar = document.getElementById('mobileSidebar');
    if (!sidebar) return;
    sidebar.classList.remove('active');
    document.getElementById('sidebarOverlay').classList.remove('active');
    document.body.style.overflow = '';
}

// Show sidebar on mobile after DOM is ready
showSidebarOnMobile();
window.addEventListener('resize', () => {
    const sidebar = document.getElementById('mobileSidebar');
    if (!sidebar) return;
    if (window.innerWidth >= 1200) {
        sidebar.style.display = 'none';
        sidebar.classList.remove('active');
        document.getElementById('sidebarOverlay').classList.remove('active');
        document.body.style.overflow = '';
    } else {
        sidebar.style.display = 'flex';
    }
});

// Close sidebar on Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeSidebar();
});

// ================================================================
// ANIMATED COUNTERS (KPI values)
// ================================================================
function animateCounters() {
    const counters = document.querySelectorAll('.kpi-value[data-target]');
    if (!counters.length) return;

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const el = entry.target;
                const target = parseInt(el.getAttribute('data-target'), 10);
                if (isNaN(target) || target === 0) {
                    el.textContent = '0';
                    observer.unobserve(el);
                    return;
                }
                animateValue(el, 0, target, 800);
                observer.unobserve(el);
            }
        });
    }, { threshold: 0.3 });

    counters.forEach(c => observer.observe(c));
}

function animateValue(el, start, end, duration) {
    const startTime = performance.now();
    const isFloat = String(end).includes('.');

    function update(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);
        // Ease out cubic
        const eased = 1 - Math.pow(1 - progress, 3);
        const current = Math.floor(start + (end - start) * eased);

        if (isFloat) {
            el.textContent = current.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        } else {
            el.textContent = current.toLocaleString('pt-BR');
        }

        if (progress < 1) {
            requestAnimationFrame(update);
        } else {
            el.textContent = end.toLocaleString('pt-BR');
        }
    }

    requestAnimationFrame(update);
}
