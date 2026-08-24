document.addEventListener('DOMContentLoaded', function () {

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
            document.body.classList.add('sidebar-lock-scroll');
        }
        function cerrarSidebar() {
            sidebar.classList.remove('sidebar-open');
            backdrop.classList.remove('show');
            toggle.setAttribute('aria-expanded', 'false');
            document.body.classList.remove('sidebar-lock-scroll');
        }
        toggle.addEventListener('click', () => {
            sidebar.classList.contains('sidebar-open') ? cerrarSidebar() : abrirSidebar();
        });
        backdrop.addEventListener('click', cerrarSidebar);
        sidebar.querySelectorAll('a').forEach(a => a.addEventListener('click', cerrarSidebar));
        window.addEventListener('resize', () => {
            if (window.innerWidth > 900) cerrarSidebar();
        });
    }

});
