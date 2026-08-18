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

// ── ENTER → SIGUIENTE CAMPO ──────────────────────────────────
// En los formularios del módulo (depósitos, recaudaciones, ganancias,
// cobros...) los campos no viven dentro de un <form>, así que Enter no
// hacía nada. Acá se emula el comportamiento de Tab: al presionar Enter
// en un input/select, el foco pasa al siguiente campo visible del
// documento. No pisa los campos que ya manejan Enter a mano (dropdowns
// de autocompletado, búsquedas, etc.) porque esos llaman
// e.preventDefault() antes de que este handler (agregado al final, a
// nivel document) llegue a evaluarse.
(function () {
    'use strict';

    const TIPOS_EXCLUIDOS = ['button', 'submit', 'reset', 'checkbox', 'radio', 'hidden', 'file', 'image'];

    function esVisible(el) {
        return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
    }

    function esCampoNavegable(el) {
        if (!(el instanceof HTMLElement)) return false;
        if (el.disabled || el.readOnly) return false;
        if (el.tagName === 'SELECT') return true;
        if (el.tagName === 'INPUT') return !TIPOS_EXCLUIDOS.includes(el.type);
        return false;
    }

    function siguienteCampo(actual) {
        const campos = Array.from(document.querySelectorAll('input, select'))
            .filter(el => esCampoNavegable(el) && esVisible(el));
        const idx = campos.indexOf(actual);
        if (idx === -1) return null;
        return campos[idx + 1] || null;
    }

    document.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter' || e.defaultPrevented) return;
        if (e.shiftKey || e.ctrlKey || e.altKey || e.metaKey) return;
        if (!esCampoNavegable(e.target)) return;

        const siguiente = siguienteCampo(e.target);
        if (!siguiente) return;

        e.preventDefault();
        siguiente.focus();
        if (typeof siguiente.select === 'function') siguiente.select();
    });
})();