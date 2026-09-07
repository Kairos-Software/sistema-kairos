// Sitio público Grupo Kairos — menú de navegación en mobile.
// Sin JS, los links quedan visibles (apilados); el JS solo agrega
// el colapso con botón hamburguesa.
(function () {
    'use strict';
    document.documentElement.classList.add('js');

    var toggle = document.querySelector('.pu-nav__toggle');
    var links  = document.getElementById('pu-links');
    if (!toggle || !links) return;

    function setOpen(open) {
        links.classList.toggle('is-open', open);
        toggle.setAttribute('aria-expanded', String(open));
    }

    toggle.addEventListener('click', function () {
        setOpen(!links.classList.contains('is-open'));
    });

    // Cerrar al elegir un link o al tocar fuera.
    links.addEventListener('click', function (e) {
        if (e.target.closest('a')) setOpen(false);
    });
    document.addEventListener('click', function (e) {
        if (!e.target.closest('.pu-nav')) setOpen(false);
    });
    window.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') setOpen(false);
    });
})();
