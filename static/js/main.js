
/* =====================================
   ENTRECOL+ - JAVASCRIPT PRINCIPAL
===================================== */

document.addEventListener("DOMContentLoaded", function () {

    const menuToggle = document.getElementById("menu-toggle");
    const sidebar = document.querySelector(".sidebar");
    const menuItems = document.querySelectorAll(".menu-item");

    // Abrir y cerrar el menú lateral.
    if (menuToggle && sidebar) {
        menuToggle.addEventListener("click", function () {
            sidebar.classList.toggle("open");

            const abierto = sidebar.classList.contains("open");
            menuToggle.setAttribute("aria-expanded", abierto);
        });
    }

    // Cerrar el menú al seleccionar una opción en celular.
    menuItems.forEach(function (item) {
        item.addEventListener("click", function () {
            if (window.innerWidth <= 900 && sidebar) {
                sidebar.classList.remove("open");

                if (menuToggle) {
                    menuToggle.setAttribute("aria-expanded", "false");
                }
            }
        });
    });

    // Cerrar el menú al ampliar la ventana.
    window.addEventListener("resize", function () {
        if (window.innerWidth > 900 && sidebar) {
            sidebar.classList.remove("open");

            if (menuToggle) {
                menuToggle.setAttribute("aria-expanded", "false");
            }
        }
    });

});
