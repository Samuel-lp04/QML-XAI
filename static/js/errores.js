const formulario = document.querySelector('form[action="/crear_proyecto"]');
const divErrores = document.getElementById('erroresFormulario');
const selectModelo = document.getElementById('modelo');
const selectTipo = document.getElementById('tipoModelo');
const selectOptimizador = document.getElementById('optimizador');

if (formulario) {
    formulario.addEventListener('submit', function (evento) {
        const errores = [];

        if (!selectModelo.value) {
            errores.push('Debes seleccionar un tipo de modelo (nuevo o usado).');
        } else if (selectModelo.value === 'nuevo') {

            const nombreModelo = document.getElementById('nombre_modelo');
            if (!nombreModelo.value.trim()) {
                errores.push('El nombre del modelo es obligatorio.');
            }

            if (!selectTipo.value) {
                errores.push('Debes seleccionar el tipo de modelo (QNN o QSVR).');
            } else if (selectTipo.value === 'QNN') {

                if (!document.getElementById('reps').value) {
                    errores.push('Las repeticiones del circuito son obligatorias.');
                }
                if (!selectOptimizador.value) {
                    errores.push('Debes seleccionar un optimizador.');
                } else {
                    const campos = {
                        'L_BFGS_B': ['max_iter_lbfgs', 'ftol_lbfgs'],
                        'COBYLA': ['max_iter_cobyla', 'rhobeg_cobyla', 'tol_cobyla'],
                        'SPSA': ['max_iter_spsa', 'learning_rate_spsa', 'perturbacion_spsa']
                    };
                    for (const parametro of campos[selectOptimizador.value]) {
                        if (!document.getElementById(parametro).value) {
                            errores.push(`Falta completar el campo "${parametro}" del optimizador.`);
                        }
                    }
                }

            } else if (selectTipo.value === 'QSVR') {
                for (const parametro of ['C_qsvr', 'epsilon_qsvr', 'max_iter_qsvr', 'tol_qsvr']) {
                    if (!document.getElementById(parametro).value) {
                        errores.push(`Falta completar el campo "${parametro}" del QSVR.`);
                    }
                }
            }
        } else if (selectModelo.value === 'usado') {
            if (!document.getElementById('modelo_usado').value) {
                errores.push('Debes seleccionar uno de tus modelos guardados.');
            }
        }
        const nombreProyecto = document.getElementById('nombre_proyecto');
        if (!nombreProyecto.value.trim()) {
            errores.push('El nombre del proyecto es obligatorio.');
        }

        const gsi = document.getElementById('GSI');
        if (!gsi.disabled && !gsi.value) {
            errores.push('Debes seleccionar un Gate Significance Index.');
        }

        const datasetExistente = document.getElementById('dataset_existente');
        const datasetNuevo = document.getElementById('dataset_nuevo');
        if (!datasetExistente.value && datasetNuevo.files.length === 0) {
            errores.push('Debes seleccionar un dataset de la nube o subir uno nuevo.');
        }

        if (errores.length > 0) {
            evento.preventDefault();
            divErrores.innerHTML = errores.map(e => `<div>• ${e}</div>`).join('');
            divErrores.classList.remove('d-none');
            divErrores.scrollIntoView({ behavior: 'smooth' });
        } else {
            divErrores.classList.add('d-none');
        }
    });
}