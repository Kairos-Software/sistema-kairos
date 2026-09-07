document.addEventListener('DOMContentLoaded', function () {

    // ══ LIGHTBOX ══
    let _lbImages = [], _lbIdx = 0;

    const lb       = document.getElementById('lightbox');
    const lbImg    = document.getElementById('lbImg');
    const lbCap    = document.getElementById('lbCaption');
    const lbCnt    = document.getElementById('lbCounter');
    const lbPrev   = document.getElementById('lbPrev');
    const lbNext   = document.getElementById('lbNext');
    const lbClose  = document.getElementById('lbClose');

    function recolectar() {
        _lbImages = Array.from(document.querySelectorAll('.galeria-item img')).map(img => ({
            url:     img.src,
            caption: img.closest('.galeria-item')
                        ?.querySelector('.galeria-tipo')
                        ?.textContent?.trim() || ''
        }));
    }

    function mostrar(idx) {
        if (!lb || !_lbImages.length) return;
        _lbIdx = idx;
        lb.classList.add('active');
        document.body.style.overflow = 'hidden';

        lbImg.style.opacity = '0';
        lbImg.src = _lbImages[idx].url;
        lbImg.onload = () => { lbImg.style.opacity = '1'; };
        if (lbImg.complete && lbImg.naturalWidth) lbImg.style.opacity = '1';

        if (lbCap) lbCap.textContent = _lbImages[idx].caption;
        if (lbCnt) lbCnt.textContent = _lbImages.length > 1 ? `${idx + 1} / ${_lbImages.length}` : '';
        if (lbPrev) lbPrev.style.visibility = _lbImages.length > 1 ? 'visible' : 'hidden';
        if (lbNext) lbNext.style.visibility = _lbImages.length > 1 ? 'visible' : 'hidden';
    }

    function cerrar() {
        if (lb) lb.classList.remove('active');
        document.body.style.overflow = '';
    }

    document.addEventListener('click', function (e) {
        const item = e.target.closest('.galeria-item');
        if (!item) return;

        const img = item.querySelector('img');
        if (!img) return;

        recolectar();
        const idx = _lbImages.findIndex(i => i.url === img.src);
        mostrar(idx >= 0 ? idx : 0);
    });

    if (lbClose) lbClose.addEventListener('click', cerrar);
    if (lb) lb.addEventListener('click', e => {
        if (e.target === lb) cerrar();
    });
    if (lbPrev) lbPrev.addEventListener('click', e => {
        e.stopPropagation();
        mostrar((_lbIdx - 1 + _lbImages.length) % _lbImages.length);
    });
    if (lbNext) lbNext.addEventListener('click', e => {
        e.stopPropagation();
        mostrar((_lbIdx + 1) % _lbImages.length);
    });
    document.addEventListener('keydown', e => {
        if (!lb?.classList.contains('active')) return;
        if (e.key === 'Escape')     cerrar();
        if (e.key === 'ArrowLeft')  mostrar((_lbIdx - 1 + _lbImages.length) % _lbImages.length);
        if (e.key === 'ArrowRight') mostrar((_lbIdx + 1) % _lbImages.length);
    });

    // ══ MAPA LEAFLET ══
    if (typeof window.clienteLatitud !== 'undefined' && document.getElementById('mapaDetalle')) {
        const mapa = L.map('mapaDetalle', { zoomControl: true, scrollWheelZoom: false })
            .setView([window.clienteLatitud, window.clienteLongitud], 16);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap', maxZoom: 19
        }).addTo(mapa);
        L.marker([window.clienteLatitud, window.clienteLongitud])
            .addTo(mapa).bindPopup('Ubicación del cliente').openPopup();
    }

    // ══ SERVICIOS CONTRATADOS ══
    (function () {
        const card = document.getElementById('serviciosCard');
        if (!card) return;

        const URL_SERVICIOS = window.clienteServiciosUrl;
        const puedeEditar   = window.puedeEditarServicios === true;

        const list   = document.getElementById('scList');
        const empty  = document.getElementById('scEmpty');
        const count  = document.getElementById('scCount');
        const modalEl = document.getElementById('servicioModal');
        const form    = document.getElementById('formServicio');
        const errBox  = document.getElementById('scErrores');
        const titulo  = document.getElementById('servicioModalTitulo');
        const bsModal = (puedeEditar && modalEl && window.bootstrap)
            ? new bootstrap.Modal(modalEl) : null;

        function getCookie(name) {
            let v = null;
            document.cookie.split(';').forEach(c => {
                const [k, val] = c.trim().split('=');
                if (k === name) v = decodeURIComponent(val);
            });
            return v;
        }

        function esc(s) {
            return String(s ?? '').replace(/[&<>"']/g, m => ({
                '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
            }[m]));
        }

        function itemHtml(s) {
            const acciones = puedeEditar ? `
                <div class="sc-item-actions">
                    <button type="button" class="sc-mini sc-edit" data-id="${s.id}">Editar</button>
                    <button type="button" class="sc-mini sc-del" data-id="${s.id}" data-nombre="${esc(s.nombre)}">Eliminar</button>
                </div>` : '';
            return `
            <div class="sc-item" data-id="${s.id}"
                 data-area="${esc(s.area)}" data-nombre="${esc(s.nombre)}"
                 data-descripcion="${esc(s.descripcion)}" data-identificador="${esc(s.identificador)}"
                 data-estado="${esc(s.estado)}" data-monto="${esc(s.monto_mensual)}"
                 data-alta="${esc(s.fecha_alta)}" data-baja="${esc(s.fecha_baja)}"
                 data-observaciones="${esc(s.observaciones)}">
                <div class="sc-item-main">
                    <div class="sc-item-head">
                        <span class="sc-area-badge sc-area-${esc(s.area)}">${esc(s.area_display)}</span>
                        <span class="estado-badge estado-${esc(s.estado)}">${esc(s.estado_display)}</span>
                    </div>
                    <span class="sc-item-nombre">${esc(s.nombre)}</span>
                    ${s.identificador ? `<span class="sc-item-id">N.º ${esc(s.identificador)}</span>` : ''}
                    ${s.descripcion ? `<span class="sc-item-desc">${esc(s.descripcion)}</span>` : ''}
                </div>
                ${acciones}
            </div>`;
        }

        function refrescarEstado() {
            const n = list.querySelectorAll('.sc-item').length;
            count.textContent = n;
            empty.style.display = n ? 'none' : '';
        }

        function upsertItem(s) {
            const existente = list.querySelector(`.sc-item[data-id="${s.id}"]`);
            const tmp = document.createElement('div');
            tmp.innerHTML = itemHtml(s).trim();
            const nuevo = tmp.firstElementChild;
            if (existente) existente.replaceWith(nuevo);
            else list.appendChild(nuevo);
            refrescarEstado();
        }

        if (!puedeEditar) return;

        const btnAdd = document.getElementById('scBtnAdd');

        function abrirModal(datos) {
            errBox.style.display = 'none';
            errBox.textContent = '';
            form.reset();
            form.servicio_pk.value       = datos?.id   || '';
            form.area.value              = datos?.area  || 'cobranzas';
            form.estado.value            = datos?.estado || 'activo';
            form.nombre.value            = datos?.nombre || '';
            form.descripcion.value       = datos?.descripcion || '';
            form.identificador.value     = datos?.identificador || '';
            form.monto_mensual.value     = datos?.monto || '';
            form.fecha_alta.value        = datos?.alta || '';
            form.fecha_baja.value        = datos?.baja || '';
            form.observaciones.value     = datos?.observaciones || '';
            titulo.textContent = datos ? 'Editar servicio contratado' : 'Nuevo servicio contratado';
            bsModal.show();
        }

        if (btnAdd) btnAdd.addEventListener('click', () => abrirModal(null));

        list.addEventListener('click', async function (e) {
            const editBtn = e.target.closest('.sc-edit');
            const delBtn  = e.target.closest('.sc-del');

            if (editBtn) {
                const it = editBtn.closest('.sc-item');
                abrirModal({
                    id: it.dataset.id, area: it.dataset.area, estado: it.dataset.estado,
                    nombre: it.dataset.nombre, descripcion: it.dataset.descripcion,
                    identificador: it.dataset.identificador, monto: it.dataset.monto,
                    alta: it.dataset.alta, baja: it.dataset.baja,
                    observaciones: it.dataset.observaciones,
                });
                return;
            }

            if (delBtn) {
                const nombre = delBtn.dataset.nombre || 'este servicio';
                if (!confirm(`¿Eliminar "${nombre}"? Esta acción no se puede deshacer.`)) return;
                const fd = new FormData();
                fd.append('_action', 'eliminar');
                fd.append('servicio_pk', delBtn.dataset.id);
                delBtn.disabled = true;
                try {
                    const r = await fetch(URL_SERVICIOS, {
                        method: 'POST',
                        headers: { 'X-CSRFToken': getCookie('csrftoken') },
                        body: fd,
                    });
                    if (r.ok) {
                        delBtn.closest('.sc-item').remove();
                        refrescarEstado();
                    } else {
                        alert('No se pudo eliminar el servicio.');
                        delBtn.disabled = false;
                    }
                } catch (_) {
                    alert('Error de conexión.');
                    delBtn.disabled = false;
                }
            }
        });

        form.addEventListener('submit', async function (e) {
            e.preventDefault();
            errBox.style.display = 'none';
            const btn = document.getElementById('scGuardar');
            btn.disabled = true;
            try {
                const r = await fetch(URL_SERVICIOS, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': getCookie('csrftoken') },
                    body: new FormData(form),
                });
                const data = await r.json();
                if (r.ok && data.success) {
                    upsertItem(data.servicio);
                    bsModal.hide();
                } else {
                    const errs = data.errors
                        ? Object.entries(data.errors).map(([k, v]) => `${k}: ${v.join(' ')}`).join(' · ')
                        : (data.error || 'No se pudo guardar.');
                    errBox.textContent = errs;
                    errBox.style.display = '';
                }
            } catch (_) {
                errBox.textContent = 'Error de conexión.';
                errBox.style.display = '';
            } finally {
                btn.disabled = false;
            }
        });
    })();

});