/**
 * historial_eliminar.js
 * Lógica de eliminación de registros compartida entre
 * historial_turnos, historial_cierres e historial_depositos.
 *
 * Ubición sugerida: static/cobranzas/js/historial_eliminar.js
 *
 * Requiere:
 *  - data-eliminar-url   en el <div id="histEliminarConfig">
 *  - Bootstrap cargado (se inicializa lazy, no en DOMContentLoaded)
 */
(function () {
    'use strict';

    /* ── Esperar a que el DOM esté listo ── */
    document.addEventListener('DOMContentLoaded', function () {

        /* ── Config inyectada desde el template ── */
        const cfg = document.getElementById('histEliminarConfig');
        if (!cfg) return;   // página sin funcionalidad de eliminación

        const ELIMINAR_URL  = cfg.dataset.eliminarUrl;
        const LABEL_SINGULAR = cfg.dataset.labelSingular || 'registro';
        const LABEL_PLURAL   = cfg.dataset.labelPlural   || 'registros';

        /* ── Refs DOM ── */
        const checkTodos = document.getElementById('checkTodos');
        const btnElim    = document.getElementById('btnEliminarSeleccionados');
        const selCount   = document.getElementById('selCount');
        const elimTexto  = document.getElementById('elimTexto');
        const elimError  = document.getElementById('elimError');
        const btnConf    = document.getElementById('btnConfirmarElim');
        const modalEl    = document.getElementById('modalEliminar');

        if (!modalEl || !btnConf) return;

        /* ── Helpers ── */
        function getCsrf() {
            return document.cookie.split(';').map(c => c.trim())
                .find(c => c.startsWith('csrftoken='))?.split('=')[1] || '';
        }
        function postJSON(url, body) {
            return fetch(url, {
                method: 'POST',
                headers: { 'X-CSRFToken': getCsrf(), 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
        }
        /* Inicialización lazy: Bootstrap ya está disponible cuando se llama */
        function getModal() {
            return bootstrap.Modal.getOrCreateInstance(modalEl);
        }

        /* ── Selección masiva ── */
        function getSeleccionados() {
            return [...document.querySelectorAll('.check-item:checked')]
                .map(c => parseInt(c.dataset.id));
        }
        function actualizarBarra() {
            if (!btnElim) return;
            const n = getSeleccionados().length;
            btnElim.style.display = n ? '' : 'none';
            if (selCount) selCount.textContent = n;
        }

        checkTodos?.addEventListener('change', function () {
            document.querySelectorAll('.check-item').forEach(c => c.checked = this.checked);
            actualizarBarra();
        });
        document.querySelectorAll('.check-item').forEach(c =>
            c.addEventListener('change', actualizarBarra)
        );

        /* ── Abrir modal ── */
        let idsAEliminar = [];

        const ICONO_SVG = `<svg viewBox="0 0 16 16" fill="none" width="13" height="13">
            <path d="M2 4h12M5 4V3a1 1 0 011-1h4a1 1 0 011 1v1M6 7v5M10 7v5"
                  stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        </svg>`;

        function abrirEliminar(ids) {
            idsAEliminar = ids;
            const label  = ids.length === 1 ? LABEL_SINGULAR : LABEL_PLURAL;
            elimTexto.textContent   = ids.length === 1
                ? `¿Eliminás el ${LABEL_SINGULAR} #${ids[0]}?`
                : `¿Eliminás los ${ids.length} ${label} seleccionados?`;
            elimError.style.display = 'none';
            btnConf.disabled        = false;
            btnConf.innerHTML       = `${ICONO_SVG} Eliminar`;
            getModal().show();
        }

        /* Botón por fila */
        document.querySelectorAll('.btn-eliminar-fila').forEach(btn =>
            btn.addEventListener('click', () => abrirEliminar([parseInt(btn.dataset.id)]))
        );
        /* Botón masivo */
        btnElim?.addEventListener('click', () => {
            const ids = getSeleccionados();
            if (ids.length) abrirEliminar(ids);
        });

        /* ── Confirmar ── */
        btnConf.addEventListener('click', async function () {
            this.disabled    = true;
            this.textContent = 'Eliminando…';
            elimError.style.display = 'none';
            try {
                const res  = await postJSON(ELIMINAR_URL, { ids: idsAEliminar });
                const data = await res.json();
                if (data.success) {
                    idsAEliminar.forEach(id =>
                        document.querySelector(`.hist-fila[data-id="${id}"]`)?.remove()
                    );
                    getModal().hide();
                    if (checkTodos) checkTodos.checked = false;
                    actualizarBarra();
                    /* Actualizar subtítulo */
                    const n   = document.querySelectorAll('.hist-fila').length;
                    const sub = document.getElementById('subtituloHistorial');
                    if (sub) {
                        const lbl = n === 1 ? LABEL_SINGULAR : LABEL_PLURAL;
                        sub.textContent = `${n} ${lbl} encontrado${n !== 1 ? 's' : ''}`;
                    }
                } else {
                    elimError.textContent   = data.error || 'No se pudo eliminar.';
                    elimError.style.display = '';
                    this.disabled    = false;
                    this.innerHTML   = `${ICONO_SVG} Eliminar`;
                }
            } catch {
                elimError.textContent   = 'Error de conexión. Intentá de nuevo.';
                elimError.style.display = '';
                this.disabled    = false;
                this.innerHTML   = `${ICONO_SVG} Eliminar`;
            }
        });

    }); // fin DOMContentLoaded
})();