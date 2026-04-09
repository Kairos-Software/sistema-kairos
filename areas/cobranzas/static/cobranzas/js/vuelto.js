// ═══════════════════════════════════════════════════════════
// CALCULADORA DE VUELTO — vuelto.js
// Panel flotante. Atajo: Alt+V
// Solo se activa dentro del módulo Cobranzas (.cobranzas-layout)
// ═══════════════════════════════════════════════════════════

(function () {
    'use strict';

    function fmt(n) {
        return '$ ' + Math.abs(n).toLocaleString('es-AR', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    function construirPanel() {
        const panel = document.createElement('div');
        panel.id = 'vueltoPanel';
        panel.setAttribute('role', 'dialog');
        panel.setAttribute('aria-label', 'Calculadora de vuelto');

        panel.innerHTML = `
            <div class="vp-header" id="vpHeader">
                <span class="vp-icon">↩️</span>
                <h6>Calculadora de Vuelto</h6>
                <div class="vp-header-acciones">
                    <button class="vp-btn-minimizar" id="vpMinimizar" title="Minimizar">
                        <svg viewBox="0 0 12 12" fill="none" width="12" height="12">
                            <path d="M2 6h8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                        </svg>
                    </button>
                    <button class="vp-close" id="vpClose" title="Cerrar (Esc)">
                        <svg viewBox="0 0 12 12" fill="none" width="11" height="11">
                            <path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
                        </svg>
                    </button>
                </div>
            </div>

            <div class="vp-minimizado-bar" id="vpMinimizadoBar">
                <span class="vp-mini-label">Vuelto:</span>
                <span class="vp-mini-total" id="vpMiniTotal">$ 0,00</span>
                <button class="vp-btn-expandir" id="vpExpandir">
                    <svg viewBox="0 0 12 12" fill="none" width="10" height="10">
                        <path d="M6 2v8M2 6h8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                    </svg>
                    Expandir
                </button>
            </div>

            <div class="vp-body">
                <div class="vp-campo">
                    <label class="vp-label">Total a cobrar</label>
                    <div class="vp-input-wrap">
                        <span class="vp-signo">$</span>
                        <input type="number" id="vpTotal" class="vp-input"
                               min="0" step="0.01" placeholder="0,00" inputmode="decimal">
                    </div>
                </div>
                <div class="vp-campo">
                    <label class="vp-label">Entrega el cliente</label>
                    <div class="vp-input-wrap">
                        <span class="vp-signo">$</span>
                        <input type="number" id="vpEntrega" class="vp-input"
                               min="0" step="0.01" placeholder="0,00" inputmode="decimal">
                    </div>
                </div>

                <div class="vp-resultado" id="vpResultado">
                    <div class="vp-resultado-label" id="vpResultadoLabel">Vuelto</div>
                    <div class="vp-resultado-monto" id="vpResultadoMonto">$ 0,00</div>
                </div>
            </div>

            <div class="vp-footer">
                <button class="vp-btn-limpiar" id="vpLimpiar">Limpiar</button>
            </div>
        `;

        document.body.appendChild(panel);
        return panel;
    }

    let minimizado = false;

    function calcular() {
        const total   = parseFloat(document.getElementById('vpTotal').value)   || 0;
        const entrega = parseFloat(document.getElementById('vpEntrega').value) || 0;
        const diff    = entrega - total;

        const monto = document.getElementById('vpResultadoMonto');
        const label = document.getElementById('vpResultadoLabel');
        const mini  = document.getElementById('vpMiniTotal');
        const res   = document.getElementById('vpResultado');

        if (total <= 0 && entrega <= 0) {
            monto.textContent = '$ 0,00';
            label.textContent = 'Vuelto';
            res.className = 'vp-resultado';
            mini.textContent = '$ 0,00';
            mini.className = 'vp-mini-total';
            return;
        }

        if (diff > 0) {
            monto.textContent = fmt(diff);
            label.textContent = 'Vuelto a dar';
            res.className = 'vp-resultado vp-resultado-ok';
            mini.textContent = fmt(diff);
            mini.className = 'vp-mini-total vp-mini-ok';
        } else if (diff < 0) {
            monto.textContent = fmt(diff);
            label.textContent = 'Falta recibir';
            res.className = 'vp-resultado vp-resultado-falta';
            mini.textContent = '−' + fmt(diff);
            mini.className = 'vp-mini-total vp-mini-falta';
        } else {
            monto.textContent = '$ 0,00 — Justo';
            label.textContent = 'Sin vuelto';
            res.className = 'vp-resultado vp-resultado-justo';
            mini.textContent = 'Justo ✓';
            mini.className = 'vp-mini-total vp-mini-ok';
        }
    }

    function limpiar() {
        document.getElementById('vpTotal').value   = '';
        document.getElementById('vpEntrega').value = '';
        calcular();
        document.getElementById('vpTotal').focus();
    }

    function abrir() {
        const panel = document.getElementById('vueltoPanel');
        if (!panel) return;
        panel.classList.add('abierto');
        if (!minimizado) {
            setTimeout(() => document.getElementById('vpTotal').focus(), 60);
        }
    }

    function cerrar() {
        const panel = document.getElementById('vueltoPanel');
        if (panel) panel.classList.remove('abierto');
    }

    function toggle() {
        const panel = document.getElementById('vueltoPanel');
        if (!panel) return;
        panel.classList.contains('abierto') ? cerrar() : abrir();
    }

    function minimizar() {
        minimizado = true;
        document.getElementById('vueltoPanel').classList.add('minimizado');
    }

    function expandir() {
        minimizado = false;
        document.getElementById('vueltoPanel').classList.remove('minimizado');
        setTimeout(() => document.getElementById('vpTotal').focus(), 60);
    }

    function habilitarDrag(panel) {
        const header  = panel.querySelector('#vpHeader');
        const miniBar = panel.querySelector('#vpMinimizadoBar');
        let dragging = false, startX, startY, initLeft, initTop;

        function onMouseDown(e) {
            if (e.target.closest('#vpClose, #vpMinimizar, #vpExpandir')) return;
            dragging = true;
            startX = e.clientX; startY = e.clientY;
            const rect = panel.getBoundingClientRect();
            initLeft = rect.left; initTop = rect.top;
            document.body.style.userSelect = 'none';
        }

        header.addEventListener('mousedown', onMouseDown);
        miniBar.addEventListener('mousedown', onMouseDown);

        document.addEventListener('mousemove', e => {
            if (!dragging) return;
            panel.style.left  = Math.max(0, initLeft + (e.clientX - startX)) + 'px';
            panel.style.top   = Math.max(0, initTop  + (e.clientY - startY)) + 'px';
            panel.style.right = 'auto';
        });

        document.addEventListener('mouseup', () => {
            dragging = false;
            document.body.style.userSelect = '';
        });
    }

    document.addEventListener('DOMContentLoaded', () => {
        if (!document.querySelector('.cobranzas-layout')) return;

        const panel = construirPanel();

        // Calcular en tiempo real
        panel.querySelector('#vpTotal').addEventListener('input', calcular);
        panel.querySelector('#vpEntrega').addEventListener('input', calcular);

        // Tab en "Total a cobrar" → salta a "Entrega"
        panel.querySelector('#vpTotal').addEventListener('keydown', e => {
            if (e.key === 'Tab') {
                e.preventDefault();
                document.getElementById('vpEntrega').focus();
            }
        });

        panel.querySelector('#vpClose').addEventListener('click', cerrar);
        panel.querySelector('#vpLimpiar').addEventListener('click', limpiar);
        panel.querySelector('#vpMinimizar').addEventListener('click', minimizar);
        panel.querySelector('#vpExpandir').addEventListener('click', expandir);

        panel.addEventListener('keydown', e => {
            if (e.key === 'Escape') cerrar();
        });

        habilitarDrag(panel);

        // Botón sidebar
        const btnSidebar = document.getElementById('btnVuelto');
        if (btnSidebar) btnSidebar.addEventListener('click', toggle);

        // Atajo Alt+V
        document.addEventListener('keydown', e => {
            if (!e.altKey || !(e.key === 'v' || e.key === 'V')) return;
            const tag = document.activeElement.tagName;
            const esInputAjeno = (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT')
                && !document.activeElement.classList.contains('vp-input');
            if (esInputAjeno) return;
            e.preventDefault();
            toggle();
        });
    });

})();