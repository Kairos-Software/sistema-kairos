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

    const modalEl     = document.getElementById('notaModal');
    const modal       = modalEl ? new bootstrap.Modal(modalEl) : null;
    const elimModalEl = document.getElementById('eliminarNotaModal');
    const elimModal   = elimModalEl ? new bootstrap.Modal(elimModalEl) : null;
    const verModalEl  = document.getElementById('verNotaModal');
    const verModal    = verModalEl ? new bootstrap.Modal(verModalEl) : null;
    const form        = document.getElementById('formNota');
    const btnNuevo    = document.getElementById('btnNuevaNota');
    const errores     = document.getElementById('notaErrores');

    // ─── Ver contenido ──────────────────────────────────────────────────
    document.querySelectorAll('.btn-ver').forEach(btn => {
        btn.addEventListener('click', () => {
            const row = btn.closest('tr');
            document.getElementById('verNotaTitulo').textContent = row.dataset.titulo;
            document.getElementById('verNotaContenido').textContent = row.dataset.contenido || '';
            verModal.show();
        });
    });

    document.getElementById('btnCopiarNota')?.addEventListener('click', async () => {
        const texto = document.getElementById('verNotaContenido').textContent;
        try {
            await navigator.clipboard.writeText(texto);
            const btn = document.getElementById('btnCopiarNota');
            const original = btn.textContent;
            btn.textContent = 'Copiado';
            setTimeout(() => { btn.textContent = original; }, 1500);
        } catch { /* clipboard no disponible */ }
    });

    // ─── Alta / edición ─────────────────────────────────────────────────

    function abrirNuevo() {
        if (!form) return;
        form.reset();
        document.getElementById('notaPk').value = '';
        document.getElementById('notaModalTitulo').textContent = 'Nueva nota';
        errores.style.display = 'none';
        modal.show();
    }

    function abrirEditar(row) {
        if (!form) return;
        form.reset();
        document.getElementById('notaPk').value = row.dataset.id;
        document.getElementById('notaTitulo').value = row.dataset.titulo;
        document.getElementById('notaContenido').value = row.dataset.contenido;
        document.getElementById('notaModalTitulo').textContent = 'Editar nota';
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

        const resp = await postForm(window.softwareUrls.notaAcciones, fd);
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
            document.getElementById('eliminarNotaNombre').textContent = btn.dataset.nombre;
            document.getElementById('eliminarNotaError').style.display = 'none';
            elimModal.show();
        });
    });

    document.getElementById('btnConfirmarEliminarNota')?.addEventListener('click', async () => {
        if (!pkEliminar) return;
        const fd = new FormData();
        fd.set('pk', pkEliminar);
        const resp = await postForm(window.softwareUrls.notaEliminar, fd);
        const data = await resp.json();
        if (data.success) {
            window.location.reload();
        } else {
            const err = document.getElementById('eliminarNotaError');
            err.style.display = 'block';
            err.textContent = data.error || 'No se pudo eliminar.';
        }
    });

});
