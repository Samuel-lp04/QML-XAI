import io
from pmlb import fetch_data
import pandas as pd
from GSI import QSVRTest, QSVRTrain, calculate_GSI_F, calculate_GSI_E, create_feature_map, remove_low_M_gates, QNNTrain, QNNTest, plot_circuit_with_metrics, plot_circuit
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler, StandardScaler
from qiskit_algorithms.utils import algorithm_globals
import os
import time
import math

SEMILLA = 42
MAX_FEATURES = int(os.getenv('MAX_FEATURES', '10'))
MIN_FILAS = 10


def leer_dataset(contenido):
    """
    Lee un dataset (CSV, TSV o similar; el separador se detecta solo) y lo valida.
    La última columna es la variable objetivo y el resto son las features.
    Lanza ValueError con un mensaje legible si el fichero no es válido.
    """
    if not contenido:
        raise ValueError('el fichero está vacío.')
    try:
        df = pd.read_csv(io.BytesIO(contenido), sep=None, engine='python')
    except Exception as e:
        raise ValueError(f'no se ha podido leer el fichero ({e}).')

    if df.shape[1] < 2:
        raise ValueError('hacen falta al menos 2 columnas (features + variable objetivo). '
                         'Comprueba que el separador sea coma, punto y coma o tabulador.')
    num_features = df.shape[1] - 1
    if num_features > MAX_FEATURES:
        raise ValueError(f'tiene {num_features} features y el máximo es {MAX_FEATURES} '
                         '(cada feature es un qubit del circuito).')
    if len(df) < MIN_FILAS:
        raise ValueError(f'tiene {len(df)} filas y el mínimo es {MIN_FILAS}.')

    no_numericas = [c for c in df.columns if not pd.api.types.is_numeric_dtype(df[c])]
    if no_numericas:
        raise ValueError(f'todas las columnas deben ser numéricas; no lo son: {", ".join(map(str, no_numericas))}.')
    if df.isna().any().any():
        raise ValueError('hay valores vacíos (NaN). Limpia o elimina esas filas antes de subirlo.')
    if df.iloc[:, -1].nunique() < 2:
        raise ValueError('la variable objetivo (última columna) es constante.')
    return df


def entrenamiento(dataset, config):
    algorithm_globals.random_seed = SEMILLA
    df = leer_dataset(dataset)

    y = df.iloc[:, -1]
    X = df.iloc[:, :-1]

    # Split the data into training and test sets
    X_train_full, X_test, y_train_full, y_test = train_test_split(
        X, y, test_size=0.2, random_state=SEMILLA)

    # Split the training set into training and validation
    X_train, X_val, y_train, y_val = train_test_split(
        X_train_full, y_train_full, test_size=0.25, random_state=SEMILLA)

    scaler_X = MinMaxScaler(feature_range=(0, np.pi))
    X_train = pd.DataFrame(scaler_X.fit_transform(X_train), columns=X_train.columns)
    X_val   = pd.DataFrame(scaler_X.transform(X_val),   columns=X_val.columns)
    X_test  = pd.DataFrame(scaler_X.transform(X_test),  columns=X_test.columns)

    scaler_y = StandardScaler()
    y_train = pd.Series(scaler_y.fit_transform(y_train.values.reshape(-1, 1)).ravel())
    y_val   = pd.Series(scaler_y.transform(y_val.values.reshape(-1, 1)).ravel())
    y_test  = pd.Series(scaler_y.transform(y_test.values.reshape(-1, 1)).ravel())

    enfoque = config['GSI']
    print(f"Enfoque recibido: {repr(enfoque)}")

    num_qubit = X_train.shape[1]

    print(f"The number of qubits for the dataset is {num_qubit}")

    qc = create_feature_map(num_qubit)

    numero_de_puertas = len(qc.decompose().data)
    print(f"The circuit has {numero_de_puertas} gates.")

    if enfoque == "F":
        time_init = time.time()
        metrics = calculate_GSI_F(qc.decompose(), X_train.iloc[0].values)
        time_end = time.time()
    elif enfoque == "E":
        time_init = time.time()
        metrics = calculate_GSI_E(qc.decompose(), X_train.iloc[0].values)
        time_end = time.time()
    else:
        raise ValueError(f"Enfoque GSI no válido: {enfoque!r} (debe ser 'F' o 'E')")

    print(f"The time to compute the GSI is {time_end - time_init}")

    for m in metrics:
        print(f"Gate: {m['gate']} at position {m['position']}")
        print(f"  Metric (M, {enfoque}): {m['M']:.4f}\n")

    grafica_base = plot_circuit_with_metrics(
        qc.decompose(), X_train.iloc[0].values, metrics,
        metric_name=enfoque
    )
    # Extract the values ​​of the metric M
    M_values = [m['M'] for m in metrics]

    # Calculate the minimum and maximum of M
    M_min = min(M_values)
    M_max = max(M_values)

    print(f"Metric (M): minimum = {M_min:.4f}, maximum = {M_max:.4f}")

    # Create a list of thresholds from M_min to M_max in increments of 0.02
    thresholds = np.arange(M_min, M_max + 0.02, 0.02)
    thresholds = np.round(thresholds, 4)  # Round to avoid float precision issues

    print(thresholds)

    # Dictionaries to store results, models and circuits
    results = {}
    models = {}
    circuits = {}

    last_num_puertas = None

    # Iterate over the thresholds and perform the process
    for idx, threshold in enumerate(thresholds):
        print(f"\nEvaluating with threshold M_threshold = {threshold}")
        try:

                # Remove doors with M < threshold
                new_feature_map = remove_low_M_gates(qc.decompose(), metrics, M_threshold=threshold)

                numero_de_puertas = len(new_feature_map.decompose().data)

                if last_num_puertas is not None and numero_de_puertas == last_num_puertas:
                    print(f"Skipping threshold {threshold}: same #gates ({numero_de_puertas}) as previous executed model")
                    continue

                print(
                    f"The circuit has {numero_de_puertas} gates after removing with M_threshold = {threshold}")

                # Train the model using the modified feature map - TOCAR AQUI
                if config['tipo'] == 'QNN':
                    model, score, total_time = QNNTrain(
                        X_train, y_train, X_val, y_val, new_feature_map, config)
                else:
                    model, score, total_time = QSVRTrain(
                        X_train, y_train, X_val, y_val, new_feature_map, config)

                print(
                    f"The score of the circuit with M_threshold = {threshold} is {score} and time is {total_time}")

                # Store the results, the model and the circuit
                results[threshold] = {'Threshold': float(threshold), 'Score': float(score),
                                    'Time': float(total_time), 'Num_Puertas': int(numero_de_puertas)}
                models[threshold] = model
                circuits[threshold] = new_feature_map

                last_num_puertas = numero_de_puertas

        except Exception as e:
            print(
                f"Error al evaluar el circuito con M_threshold = {threshold}: {e}")
            # Still storing the results
            results[threshold] = {'Threshold': float(threshold), 'Score': None,
                                'Time': None, 'Num_Puertas': int(numero_de_puertas)}
            models[threshold] = None
            circuits[threshold] = None

    # Convert the result dictionary to a pandas DataFrame
    results_df = pd.DataFrame.from_dict(results, orient='index')


    # Select the base circuit
    print("\nSelect the base circuit...")
    base_threshold = thresholds[0]
    base_result = results[base_threshold]
    base_MAE = base_result['Score']
    base_time = base_result['Time']
    base_circuit = circuits[base_threshold]
    print(f"Base circuit at threshold {base_threshold} with score {base_MAE} and time {base_time}")

    # Only circuits that trained correctly (Score not None) can be selected
    results_df_no_base = results_df.drop(index=base_threshold).dropna(subset=['Score'])

    if base_MAE is None and results_df_no_base.empty:
        raise RuntimeError("Ningún circuito se ha podido entrenar; revisa los parámetros del modelo y el dataset.")

    print("\nSelecting the best circuit in terms of MAE...")
    if not results_df_no_base.empty:
        # Select the model with the lowest MAE
        best_MAE_model_info = results_df_no_base.loc[results_df_no_base['Score'].idxmin()]
        best_MAE_threshold = best_MAE_model_info['Threshold']
        best_MAE_model = models[best_MAE_threshold]
        best_MAE_circuit = circuits[best_MAE_threshold]
        print(
            f"Best model in terms of MAE is at threshold {best_MAE_threshold} with score {best_MAE_model_info['Score']} and time {best_MAE_model_info['Time']}")
    else:
        # Every threshold produced the same circuit as the base one: nothing to compare
        print("There are no pruned circuits to compare with the base circuit.")
        best_MAE_model_info = None
        best_MAE_model = None
        best_MAE_circuit = None

    # Select the best circuit in terms of time
    print("\nSelecting the best circuit in terms of time...")
    if base_MAE is not None and not results_df_no_base.empty:
        max_MAE = base_MAE * 1.15  # Optional: limit to models with MAE no more than 15% worse than the base
        candidates_time = results_df_no_base[results_df_no_base['Score'] <= max_MAE] # MAE
    else:
        # Without a valid base score there is no reference for the 15% constraint
        candidates_time = results_df_no_base.iloc[0:0]

    if not candidates_time.empty:
        # Select the model with the shortest time
        best_time_model_info = candidates_time.loc[candidates_time['Time'].idxmin()]
        best_time_threshold = best_time_model_info['Threshold']
        best_time_model = models[best_time_threshold]
        best_time_circuit = circuits[best_time_threshold]
        print(
            f"Best model in terms of time is at threshold {best_time_threshold} with score {best_time_model_info['Score']} and time {best_time_model_info['Time']}")

    else:
        print("There are no models that meet the MAE constraint to optimize time.")
        best_time_model = None
        best_time_circuit = None

    
    # === Evaluation on the test set ===
    print("\n=== Evaluation on the test set ===")

    grafica_best_MAE = plot_circuit(best_MAE_circuit) if best_MAE_circuit is not None else None
    grafica_best_time = plot_circuit(best_time_circuit) if best_time_circuit is not None else None

    resultados_finales = []


    def _limpiar(v):
        if v is None or (isinstance(v, float) and not math.isfinite(v)):
            return None
        return float(v)

    def _añadir_resultado(tipo, modelo, training_time, grafica_bytes):
        if modelo is None:
            print(f"No hay modelo '{tipo}' que evaluar en test; se omite.")
            return
        if config['tipo'] == 'QNN':
            metrics, test_time = QNNTest(modelo, X_test, y_test, scaler_y)
        else:
            metrics, test_time = QSVRTest(modelo, X_test, y_test, scaler_y)
        print(f"[{tipo}] métricas en test: {metrics}")
        resultados_finales.append({
            'tipo': tipo,
            'MSE': metrics['MSE'],
            'RMSE': metrics['RMSE'],
            'MAE': metrics['MAE'],
            'MAPE': metrics['MAPE'],
            'R2': _limpiar(metrics['R2']),
            'trainingTime': training_time,
            'testingTime': test_time,
            'grafica': grafica_bytes,
        })

    _añadir_resultado('base', models[base_threshold], base_result['Time'], grafica_base)
    _añadir_resultado('best_MAE', best_MAE_model,
                      best_MAE_model_info['Time'] if best_MAE_model is not None else None, grafica_best_MAE)
    _añadir_resultado(
        'best_time',
        best_time_model,
        best_time_model_info['Time'] if best_time_model is not None else None,
        grafica_best_time,
    )

    if not resultados_finales:
        raise RuntimeError("No se ha podido evaluar ningún modelo en el conjunto de test.")

    etiquetas = {}
    if models[base_threshold] is not None:
        etiquetas.setdefault(float(base_threshold), []).append('base')
    if best_MAE_model is not None:
        etiquetas.setdefault(float(best_MAE_threshold), []).append('best_MAE')
    if best_time_model is not None:
        etiquetas.setdefault(float(best_time_threshold), []).append('best_time')

    for result in results.values():
        result['seleccion'] = etiquetas.get(result['Threshold'], [])

   
    return resultados_finales, results
