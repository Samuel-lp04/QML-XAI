document.addEventListener("DOMContentLoaded", function () {

    // Obtenemos los elementos del DOM
    const selectModelo = document.getElementById('modelo');
    const seccionNuevo = document.getElementById('seccionNuevo');
    const seccionUsado = document.getElementById('seccionUsado');

    const selectTipo = document.getElementById('tipoModelo');
    const seccionQNN = document.getElementById('seccionQNN');
    const seccionQSVR = document.getElementById('seccionQSVR');

    const selectOptimizador = document.getElementById('optimizador');
    const seccionL_BFGS_B = document.getElementById('seccionL_BFGS_B');
    const seccionCOBYLA = document.getElementById('seccionCOBYLA');
    const seccionSPSA = document.getElementById('seccionSPSA');

    if (selectModelo) {

        selectModelo.addEventListener('change', function () {

            seccionNuevo.classList.add('d-none');
            seccionUsado.classList.add('d-none');

            if (this.value === 'nuevo') {
                seccionNuevo.classList.remove('d-none');
            } else if (this.value === 'usado') {
                seccionUsado.classList.remove('d-none');
                const selectModelo = document.getElementById('modelo');
                const bloqueGSI = document.getElementById('bloqueGSI');
                const selectGSI = document.getElementById('GSI');

                function actualizarGSI() {
                    const esUsado = selectModelo.value === 'usado';
                    bloqueGSI.classList.toggle('d-none', esUsado);
                    selectGSI.required = !esUsado;
                    selectGSI.disabled = esUsado;
                }

                selectModelo.addEventListener('change', actualizarGSI);
                actualizarGSI();
            }
        });
    }
    if (selectTipo) {
        selectTipo.addEventListener('change', function () {
            seccionQNN.classList.add('d-none');
            seccionQSVR.classList.add('d-none');

            if (this.value === 'QNN') {
                seccionQNN.classList.remove('d-none');
            } else if (this.value === 'QSVR') {
                seccionQSVR.classList.remove('d-none');
            }
        });
    }
    if (selectOptimizador) {
        selectOptimizador.addEventListener('change', function () {
            seccionL_BFGS_B.classList.add('d-none');
            seccionCOBYLA.classList.add('d-none');
            seccionSPSA.classList.add('d-none');

            if (this.value === 'L_BFGS_B') {
                seccionL_BFGS_B.classList.remove('d-none');
            } else if (this.value === 'COBYLA') {
                seccionCOBYLA.classList.remove('d-none');
            } else if (this.value === 'SPSA') {
                seccionSPSA.classList.remove('d-none');
            }
        });
    }

});