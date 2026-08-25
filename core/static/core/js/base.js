document.addEventListener('DOMContentLoaded', function () {

    // En pantallas angostas las tablas pasan a tarjetas. Cada celda recibe
    // el nombre de su columna para que los datos sigan siendo comprensibles.
    function prepararTablasResponsive(root = document) {
        root.querySelectorAll('table.table, table.tabla-base').forEach(table => {
            if (table.dataset.responsive === 'scroll') return;

            const headers = Array.from(table.querySelectorAll('thead tr:first-child th'));
            if (!headers.length) return;

            const labels = headers.map((header, index) => {
                const text = header.textContent.replace(/\s+/g, ' ').trim();
                if (text) return text;
                if (header.querySelector('input[type="checkbox"]')) return 'Seleccionar';
                return index === headers.length - 1 ? 'Acciones' : '';
            });

            table.classList.add('responsive-card-table');
            table.querySelectorAll('tbody tr').forEach(row => {
                Array.from(row.children).forEach((cell, index) => {
                    if (cell.tagName !== 'TD' || cell.hasAttribute('data-label')) return;
                    cell.setAttribute('data-label', cell.hasAttribute('colspan') ? '' : (labels[index] || ''));
                });
            });
        });
    }

    prepararTablasResponsive();

    // Algunas pantallas agregan filas luego de guardar por AJAX.
    let actualizarTablasPendiente = false;
    const observadorTablas = new MutationObserver(mutations => {
        if (actualizarTablasPendiente || !mutations.some(m => m.addedNodes.length)) return;
        actualizarTablasPendiente = true;
        requestAnimationFrame(() => {
            prepararTablasResponsive();
            actualizarTablasPendiente = false;
        });
    });
    observadorTablas.observe(document.body, { childList: true, subtree: true });

    // ─── Sidebar de área (Cobranzas / Software): abrir/cerrar en mobile ───
    // Genérico: no hace nada en páginas sin sidebar de área (home, login,
    // gestión de usuarios/clientes, etc).
    const toggle   = document.querySelector('[data-sidebar-toggle]');
    const sidebar  = document.querySelector('[data-sidebar]');
    const backdrop = document.querySelector('[data-sidebar-backdrop]');

    if (toggle && sidebar && backdrop) {
        function abrirSidebar() {
            sidebar.classList.add('sidebar-open');
            backdrop.classList.add('show');
            toggle.setAttribute('aria-expanded', 'true');
            sidebar.setAttribute('aria-hidden', 'false');
            document.body.classList.add('sidebar-lock-scroll');
        }
        function cerrarSidebar() {
            sidebar.classList.remove('sidebar-open');
            backdrop.classList.remove('show');
            toggle.setAttribute('aria-expanded', 'false');
            sidebar.setAttribute('aria-hidden', window.innerWidth <= 991 ? 'true' : 'false');
            document.body.classList.remove('sidebar-lock-scroll');
        }
        cerrarSidebar();
        toggle.addEventListener('click', () => {
            sidebar.classList.contains('sidebar-open') ? cerrarSidebar() : abrirSidebar();
        });
        backdrop.addEventListener('click', cerrarSidebar);
        sidebar.querySelectorAll('a').forEach(a => a.addEventListener('click', cerrarSidebar));
        document.addEventListener('keydown', event => {
            if (event.key === 'Escape' && sidebar.classList.contains('sidebar-open')) cerrarSidebar();
        });
        window.addEventListener('resize', () => {
            cerrarSidebar();
        });
    }

});
