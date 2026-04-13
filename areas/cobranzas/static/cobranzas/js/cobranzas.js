// ═══════════════════════════════════════════════════════════
// COBRANZAS — cobranzas.js
// Lógica base del módulo compartida entre todas las páginas.
// ═══════════════════════════════════════════════════════════

console.log("Módulo Cobranzas cargado.");

// ── INDICADOR DE CAJA EN SIDEBAR ─────────────────────────────
// Consulta el estado de la caja al cargar cualquier página del
// módulo y actualiza el punto de color junto al ítem "Caja".
(function () {
    'use strict';

    const ind = document.getElementById('navCajaIndicator');
    if (!ind) return;

    // La URL de estado se inyecta desde base_cobranzas.html
    const url = window.cajaEstadoUrl;
    if (!url) return;

    fetch(url, {
        method: 'GET',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
    })
    .then(r => r.json())
    .then(data => {
        ind.style.display = '';
        if (data.abierta) {
            ind.className = 'nav-caja-indicator nav-caja-abierta';
            ind.title = `Caja abierta — Turno #${data.turno.numero}`;
        } else {
            ind.className = 'nav-caja-indicator nav-caja-cerrada';
            ind.title = 'Caja cerrada';
        }
    })
    .catch(() => {
        // Si falla la consulta, no mostramos el indicador
    });
})();