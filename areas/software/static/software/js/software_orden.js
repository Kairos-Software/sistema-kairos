// ═══════════════════════════════════════════════════════════════════════
// ORDENAMIENTO CLIENT-SIDE — compartido por todas las pantallas del área
// Software (VPS, Servicios, Instalaciones, Scripts).
//
// Mismo criterio que cobranzas/gestion_servicios.js: se ordena en el
// cliente (no en la DB) para evitar diferencias de collation entre
// SQLite/PostgreSQL y darle al usuario una preferencia persistente
// (localStorage) que sobrevive filtros, paginación y recargas.
// ═══════════════════════════════════════════════════════════════════════

window.SoftwareOrden = {

    /**
     * Ordena las filas <tr data-id> de un tbody según una clave "campo_dir".
     * @param {string} tbodyId
     * @param {string} clave   ej: "puerto_asc"
     * @param {object} campos  { campo: { attr: 'datasetProp', tipo: 'texto'|'numero' } }
     */
    aplicar(tbodyId, clave, campos) {
        const tbody = document.getElementById(tbodyId);
        if (!tbody || !clave) return;

        const filas = [...tbody.querySelectorAll('tr[data-id]')];
        if (!filas.length) return;

        const ultimoGuion = clave.lastIndexOf('_');
        const campo = clave.slice(0, ultimoGuion);
        const dir   = clave.slice(ultimoGuion + 1);
        const conf  = campos[campo];
        if (!conf) return;
        const asc = dir !== 'desc';

        filas.sort((a, b) => {
            let va = a.dataset[conf.attr];
            let vb = b.dataset[conf.attr];

            if (conf.tipo === 'numero') {
                va = parseFloat(va);
                vb = parseFloat(vb);
                if (isNaN(va)) va = asc ? Infinity : -Infinity;
                if (isNaN(vb)) vb = asc ? Infinity : -Infinity;
                return asc ? va - vb : vb - va;
            }

            va = (va || '').toString();
            vb = (vb || '').toString();
            const cmp = va.localeCompare(vb, 'es', { numeric: true, sensitivity: 'base' });
            return asc ? cmp : -cmp;
        });

        filas.forEach(f => tbody.appendChild(f));
    },

    /**
     * Conecta un <select id="selectOrden"> con el tbody indicado,
     * persiste la preferencia en localStorage y la aplica al cargar.
     */
    setup({ selectId, tbodyId, storageKey, campos, defaultValue }) {
        const select = document.getElementById(selectId);
        if (!select) return;

        let guardado = null;
        try { guardado = localStorage.getItem(storageKey); } catch { /* sin storage */ }
        const inicial = guardado || defaultValue || '';

        if (inicial) {
            select.value = inicial;
            this.aplicar(tbodyId, inicial, campos);
        }

        select.addEventListener('change', () => {
            try { localStorage.setItem(storageKey, select.value); } catch { /* sin storage */ }
            this.aplicar(tbodyId, select.value, campos);
        });
    },
};
