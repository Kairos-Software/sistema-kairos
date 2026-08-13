document.addEventListener('DOMContentLoaded', function () {

    function getCookie(name) {
        let v = null;
        document.cookie.split(';').forEach(c => {
            const [k, val] = c.trim().split('=');
            if (k === name) v = decodeURIComponent(val);
        });
        return v;
    }

    async function postForm(url, fd) {
        return fetch(url, {
            method: 'POST',
            headers: { 'X-CSRFToken': getCookie('csrftoken') },
            body: fd
        });
    }

    const modalEl     = document.getElementById('scriptModal');
    const modal       = modalEl ? new bootstrap.Modal(modalEl) : null;
    const elimModalEl = document.getElementById('eliminarScriptModal');
    const elimModal   = elimModalEl ? new bootstrap.Modal(elimModalEl) : null;
    const verModalEl  = document.getElementById('verScriptModal');
    const verModal    = verModalEl ? new bootstrap.Modal(verModalEl) : null;
    const form        = document.getElementById('formScript');
    const btnNuevo    = document.getElementById('btnNuevoScript');
    const errores     = document.getElementById('scriptErrores');

    // ─── Ver contenido ──────────────────────────────────────────────────
    document.querySelectorAll('.btn-ver').forEach(btn => {
        btn.addEventListener('click', () => {
            const row = btn.closest('tr');
            document.getElementById('verScriptTitulo').textContent = row.dataset.nombre;
            document.getElementById('verScriptSubtitulo').textContent = row.dataset.descripcion || '';
            document.getElementById('verScriptContenido').textContent =
                row.dataset.contenido || (row.dataset.archivo ? '(Sin contenido de texto — ver archivo adjunto)' : '');
            verModal.show();
        });
    });

    document.getElementById('btnCopiarScript')?.addEventListener('click', async () => {
        const texto = document.getElementById('verScriptContenido').textContent;
        try {
            await navigator.clipboard.writeText(texto);
            const btn = document.getElementById('btnCopiarScript');
            const original = btn.textContent;
            btn.textContent = 'Copiado ✓';
            setTimeout(() => { btn.textContent = original; }, 1500);
        } catch { /* clipboard no disponible */ }
    });

    // ─── Categoría: select con sugerencias + opción "nueva" ──────────────

    const categoriaHidden = document.getElementById('scriptCategoria');
    const categoriaSelect = document.getElementById('scriptCategoriaSelect');
    const categoriaNueva  = document.getElementById('scriptCategoriaNueva');

    function setCategoria(valor) {
        const opciones = [...categoriaSelect.options].map(o => o.value);
        if (opciones.includes(valor)) {
            categoriaSelect.value = valor;
            categoriaNueva.style.display = 'none';
            categoriaNueva.value = '';
        } else {
            categoriaSelect.value = '__nueva__';
            categoriaNueva.style.display = 'block';
            categoriaNueva.value = valor;
        }
        categoriaHidden.value = valor;
    }

    categoriaSelect?.addEventListener('change', () => {
        if (categoriaSelect.value === '__nueva__') {
            categoriaNueva.style.display = 'block';
            categoriaNueva.value = '';
            categoriaHidden.value = '';
            categoriaNueva.focus();
        } else {
            categoriaNueva.style.display = 'none';
            categoriaHidden.value = categoriaSelect.value;
        }
    });

    categoriaNueva?.addEventListener('input', () => {
        categoriaHidden.value = categoriaNueva.value;
    });

    // ─── Alta / edición ─────────────────────────────────────────────────

    function abrirNuevo() {
        if (!form) return;
        form.reset();
        document.getElementById('scriptPk').value = '';
        setCategoria('Otro');
        document.getElementById('scriptModalTitulo').textContent = 'Nuevo script';
        document.getElementById('scriptArchivoActual').textContent = '';
        errores.style.display = 'none';
        modal.show();
    }

    function abrirEditar(row) {
        if (!form) return;
        form.reset();
        document.getElementById('scriptPk').value = row.dataset.id;
        document.getElementById('scriptNombre').value = row.dataset.nombre;
        setCategoria(row.dataset.categoria);
        document.getElementById('scriptServicio').value = row.dataset.servicio;
        document.getElementById('scriptVps').value = row.dataset.vps;
        document.getElementById('scriptDescripcion').value = row.dataset.descripcion;
        document.getElementById('scriptContenido').value = row.dataset.contenido;
        document.getElementById('scriptArchivoActual').textContent =
            row.dataset.archivo ? `Archivo actual: ${row.dataset.archivo.split('/').pop()}` : '';
        document.getElementById('scriptModalTitulo').textContent = 'Editar script';
        errores.style.display = 'none';
        modal.show();
    }

    btnNuevo?.addEventListener('click', abrirNuevo);

    document.querySelectorAll('.btn-editar').forEach(btn => {
        btn.addEventListener('click', () => abrirEditar(btn.closest('tr')));
    });

    form?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const fd = new FormData(form);

        const resp = await postForm(window.softwareUrls.scriptAcciones, fd);
        const data = await resp.json();

        if (data.success) {
            window.location.reload();
        } else {
            errores.style.display = 'block';
            errores.textContent = data.errors
                ? Object.values(data.errors).flat().join(' ')
                : (data.error || 'Ocurrió un error al guardar.');
        }
    });

    // ─── Eliminar ───────────────────────────────────────────────────────

    let pkEliminar = null;

    document.querySelectorAll('.btn-eliminar').forEach(btn => {
        btn.addEventListener('click', () => {
            pkEliminar = btn.dataset.id;
            document.getElementById('eliminarScriptNombre').textContent = btn.dataset.nombre;
            document.getElementById('eliminarScriptError').style.display = 'none';
            elimModal.show();
        });
    });

    document.getElementById('btnConfirmarEliminarScript')?.addEventListener('click', async () => {
        if (!pkEliminar) return;
        const fd = new FormData();
        fd.set('pk', pkEliminar);
        const resp = await postForm(window.softwareUrls.scriptEliminar, fd);
        const data = await resp.json();
        if (data.success) {
            window.location.reload();
        } else {
            const err = document.getElementById('eliminarScriptError');
            err.style.display = 'block';
            err.textContent = data.error || 'No se pudo eliminar.';
        }
    });

});
