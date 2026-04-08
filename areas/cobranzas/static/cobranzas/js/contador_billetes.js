// ═══════════════════════════════════════════════════════════
// CONTADOR DE BILLETES — contador_billetes.js
// Solo se activa dentro del módulo Cobranzas (.cobranzas-layout)
// Atajo: Alt+B  |  Minimizar: botón "–" en el header
// ═══════════════════════════════════════════════════════════

(function () {
    'use strict';

    const BILLETES = [
        { valor: 20000, label: '$20.000' },
        { valor: 10000, label: '$10.000' },
        { valor:  5000, label: '$5.000'  },
        { valor:  2000, label: '$2.000'  },
        { valor:  1000, label: '$1.000'  },
        { valor:   500, label: '$500'    },
        { valor:   200, label: '$200'    },
        { valor:   100, label: '$100'    },
        { valor:    50, label: '$50'     },
        { valor:    20, label: '$20'     },
        { valor:    10, label: '$10'     },
    ];

    function formatearPesos(n) {
        return '$ ' + n.toLocaleString('es-AR', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        });
    }

    function construirPanel() {
        const panel = document.createElement('div');
        panel.id = 'contadorBilletesPanel';
        panel.setAttribute('role', 'dialog');
        panel.setAttribute('aria-label', 'Contador de billetes');

        panel.innerHTML = `
            <div class="cbp-header" id="cbpHeader">
                <span class="cbp-icon">💵</span>
                <h6>Contador de Billetes</h6>
                <div class="cbp-header-acciones">
                    <button class="cbp-btn-minimizar" id="cbpMinimizar" title="Minimizar">
                        <svg viewBox="0 0 12 12" fill="none" width="12" height="12">
                            <path d="M2 6h8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                        </svg>
                    </button>
                    <button class="cbp-close" id="cbpClose" title="Cerrar (Esc)">
                        <svg viewBox="0 0 12 12" fill="none" width="11" height="11">
                            <path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
                        </svg>
                    </button>
                </div>
            </div>

            <div class="cbp-minimizado-bar" id="cbpMinimizadoBar">
                <span class="cbp-mini-label">Total:</span>
                <span class="cbp-mini-total" id="cbpMiniTotal">$ 0,00</span>
                <button class="cbp-btn-expandir" id="cbpExpandir" title="Expandir">
                    <svg viewBox="0 0 12 12" fill="none" width="10" height="10">
                        <path d="M6 2v8M2 6h8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                    </svg>
                    Expandir
                </button>
            </div>

            <div class="cbp-body" id="cbpBody"></div>

            <div class="cbp-footer" id="cbpFooter">
                <div>
                    <div class="cbp-footer-label">Total Efectivo</div>
                    <div class="cbp-total-valor" id="cbpTotal">$ 0,00</div>
                </div>
                <button class="cbp-btn-limpiar" id="cbpLimpiar">Limpiar</button>
            </div>
        `;

        const body = panel.querySelector('#cbpBody');
        BILLETES.forEach(b => {
            const fila = document.createElement('div');
            fila.className = 'cbp-fila';
            fila.innerHTML = `
                <span class="cbp-denominacion">Billetes de ${b.label}:</span>
                <input type="number" class="cbp-cantidad" min="0" value=""
                       placeholder="0" data-valor="${b.valor}" inputmode="numeric">
                <span class="cbp-subtotal" data-sub="${b.valor}">—</span>
            `;
            body.appendChild(fila);
        });

        document.body.appendChild(panel);
        return panel;
    }

    let minimizado = false;

    function minimizar() {
        minimizado = true;
        document.getElementById('contadorBilletesPanel').classList.add('minimizado');
        sincronizarMiniTotal();
    }

    function expandir() {
        minimizado = false;
        const panel = document.getElementById('contadorBilletesPanel');
        panel.classList.remove('minimizado');
        const primero = panel.querySelector('.cbp-cantidad');
        if (primero) primero.focus();
    }

    function sincronizarMiniTotal() {
        const totalEl = document.getElementById('cbpTotal');
        const miniEl  = document.getElementById('cbpMiniTotal');
        if (!totalEl || !miniEl) return;
        miniEl.textContent = totalEl.textContent;
        miniEl.classList.toggle('positivo', totalEl.classList.contains('positivo'));
    }

    function actualizarTotal() {
        let total = 0;
        document.querySelectorAll('.cbp-cantidad').forEach(input => {
            const cant = parseInt(input.value) || 0;
            const val  = parseInt(input.dataset.valor);
            const sub  = cant * val;
            total += sub;
            const subEl = document.querySelector(`.cbp-subtotal[data-sub="${val}"]`);
            if (subEl) {
                if (cant > 0) {
                    subEl.textContent = formatearPesos(sub);
                    subEl.classList.add('tiene-valor');
                } else {
                    subEl.textContent = '—';
                    subEl.classList.remove('tiene-valor');
                }
            }
        });
        const totalEl = document.getElementById('cbpTotal');
        if (totalEl) {
            totalEl.textContent = formatearPesos(total);
            totalEl.classList.toggle('positivo', total > 0);
        }
        sincronizarMiniTotal();
    }

    function limpiarContador() {
        document.querySelectorAll('.cbp-cantidad').forEach(i => { i.value = ''; });
        actualizarTotal();
    }

    function abrirContador() {
        const panel = document.getElementById('contadorBilletesPanel');
        if (!panel) return;
        panel.classList.add('abierto');
        if (!minimizado) {
            const primero = panel.querySelector('.cbp-cantidad');
            if (primero) primero.focus();
        }
    }

    function cerrarContador() {
        const panel = document.getElementById('contadorBilletesPanel');
        if (panel) panel.classList.remove('abierto');
    }

    function toggleContador() {
        const panel = document.getElementById('contadorBilletesPanel');
        if (!panel) return;
        panel.classList.contains('abierto') ? cerrarContador() : abrirContador();
    }

    function habilitarDrag(panel) {
        const header  = panel.querySelector('#cbpHeader');
        const miniBar = panel.querySelector('#cbpMinimizadoBar');
        let dragging = false, startX, startY, initLeft, initTop;

        function onMouseDown(e) {
            if (e.target.closest('#cbpClose, #cbpMinimizar, #cbpExpandir')) return;
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

        panel.addEventListener('input', e => {
            if (!e.target.classList.contains('cbp-cantidad')) return;
            if (parseInt(e.target.value) < 0) e.target.value = '';
            actualizarTotal();
        });

        panel.addEventListener('keydown', e => {
            if (e.key === 'Escape') cerrarContador();
        });

        panel.querySelector('#cbpClose').addEventListener('click', cerrarContador);
        panel.querySelector('#cbpLimpiar').addEventListener('click', limpiarContador);
        panel.querySelector('#cbpMinimizar').addEventListener('click', minimizar);
        panel.querySelector('#cbpExpandir').addEventListener('click', expandir);

        habilitarDrag(panel);

        const btnSidebar = document.getElementById('btnContadorBilletes');
        if (btnSidebar) btnSidebar.addEventListener('click', toggleContador);

        document.addEventListener('keydown', e => {
            if (!e.altKey || !(e.key === 'b' || e.key === 'B')) return;
            const tag = document.activeElement.tagName;
            const esInputAjeno = (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT')
                && !document.activeElement.classList.contains('cbp-cantidad');
            if (esInputAjeno) return;
            e.preventDefault();
            toggleContador();
        });
    });

})();