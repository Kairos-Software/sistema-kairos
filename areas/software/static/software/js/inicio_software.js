document.addEventListener('DOMContentLoaded', function () {

    function getCookie(name) {
        let v = null;
        document.cookie.split(';').forEach(c => {
            const [k, val] = c.trim().split('=');
            if (k === name) v = decodeURIComponent(val);
        });
        return v;
    }

    const btnAbrir      = document.getElementById('btnAbrirImportar');
    const inputArchivo  = document.getElementById('inputBackupArchivo');
    const modalEl       = document.getElementById('importarBackupModal');
    const modal         = modalEl ? new bootstrap.Modal(modalEl) : null;
    const nombreArchivo = document.getElementById('importarBackupNombre');
    const confirmacion  = document.getElementById('importarBackupConfirmacion');
    const btnConfirmar  = document.getElementById('btnConfirmarImportarBackup');
    const errorBox      = document.getElementById('importarBackupError');

    let archivoSeleccionado = null;

    btnAbrir?.addEventListener('click', () => inputArchivo.click());

    inputArchivo?.addEventListener('change', () => {
        if (!inputArchivo.files.length) return;
        archivoSeleccionado = inputArchivo.files[0];
        nombreArchivo.textContent = archivoSeleccionado.name;
        confirmacion.value = '';
        btnConfirmar.disabled = true;
        errorBox.style.display = 'none';
        modal.show();
    });

    confirmacion?.addEventListener('input', () => {
        btnConfirmar.disabled = confirmacion.value.trim().toUpperCase() !== 'REEMPLAZAR';
    });

    btnConfirmar?.addEventListener('click', async () => {
        if (!archivoSeleccionado) return;
        btnConfirmar.disabled = true;
        btnConfirmar.textContent = 'Importando...';

        const fd = new FormData();
        fd.set('archivo', archivoSeleccionado);

        try {
            const resp = await fetch(window.softwareUrls.backupImportar, {
                method: 'POST',
                headers: { 'X-CSRFToken': getCookie('csrftoken') },
                body: fd,
            });
            const data = await resp.json();
            if (data.success) {
                window.location.reload();
            } else {
                errorBox.style.display = 'block';
                errorBox.textContent = data.error || 'No se pudo importar el backup.';
                btnConfirmar.textContent = 'Reemplazar datos';
                btnConfirmar.disabled = false;
            }
        } catch {
            errorBox.style.display = 'block';
            errorBox.textContent = 'Ocurrió un error de red al importar.';
            btnConfirmar.textContent = 'Reemplazar datos';
            btnConfirmar.disabled = false;
        } finally {
            inputArchivo.value = '';
        }
    });

});
