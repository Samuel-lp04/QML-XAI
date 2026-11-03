from qiskit.quantum_info import SparsePauliOp, Statevector, state_fidelity, entropy, partial_trace
from qiskit_algorithms.utils import algorithm_globals
from qiskit.circuit.library import EfficientSU2, ZZFeatureMap, RealAmplitudes
from qiskit import QuantumCircuit
from qiskit_machine_learning.kernels import FidelityQuantumKernel
from qiskit_machine_learning.algorithms import QSVR
from qiskit_machine_learning.neural_networks import EstimatorQNN
from qiskit_machine_learning.algorithms.regressors import NeuralNetworkRegressor
import time
import io
from qiskit_algorithms.optimizers import COBYLA, L_BFGS_B, SPSA
from qiskit.circuit import ParameterExpression
import numpy as np
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_percentage_error, mean_absolute_error, root_mean_squared_error
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D


def calculate_GSI_F(feature_map, parameter_binds):
    """
    Calculate F (fidelity), E (entanglement), S (entropy), P (sensitivity),
    and GSI (Gate Significance Index) for each gate in the quantum circuit.
    """
    # Assign parameter values to the feature map
    qc = feature_map.assign_parameters(parameter_binds).decompose()

    metrics = []
    current_qc = QuantumCircuit(qc.num_qubits)
    initial_state = Statevector.from_label('0' * qc.num_qubits)
    current_state = initial_state

    for i, instruction in enumerate(qc.data):
        gate = instruction.operation
        qubits = instruction.qubits
        params = gate.params

        qubit_indices = [qubit._index for qubit in qubits]

        # Save the previous state
        previous_state = current_state.copy()

        # Add the gate to the current circuit
        current_qc.append(gate, qubit_indices)

        # Get the new state
        current_state = Statevector.from_instruction(current_qc)

        # Calculate fidelity
        F = state_fidelity(previous_state, current_state)

        # Store metrics
        metrics.append({
            'gate': gate.name,
            'position': i,
            'M': F,
        })

    return metrics

def calculate_GSI_E(feature_map, parameter_binds):
    """
    Calculate F (fidelity), E (entanglement), S (entropy), P (sensitivity),
    and GSI (Gate Significance Index) for each gate in the quantum circuit.
    """
    # Assign parameter values to the feature map
    qc = feature_map.assign_parameters(parameter_binds).decompose()

    metrics = []
    current_qc = QuantumCircuit(qc.num_qubits)
    initial_state = Statevector.from_label('0' * qc.num_qubits)
    current_state = initial_state

    for i, instruction in enumerate(qc.data):
        gate = instruction.operation
        qubits = instruction.qubits
        params = gate.params

        qubit_indices = [qubit._index for qubit in qubits]

        # Save the previous state
        previous_state = current_state.copy()

        # Add the gate to the current circuit
        current_qc.append(gate, qubit_indices)

        # Get the new state
        current_state = Statevector.from_instruction(current_qc)

        # Calculate entanglement (normalized)
        if qc.num_qubits > 1:
            reduced_state = partial_trace(current_state, [1])
            E = entropy(reduced_state)
            max_entropy = np.log2(reduced_state.dim)
            E_normalized = E / max_entropy if max_entropy != 0 else 0
        else:
            E_normalized = 0.0

        # Store metrics
        metrics.append({
            'gate': gate.name,
            'position': i,
            'M': E_normalized,
        })

    return metrics

def results(y, y_pred):
    results_dict = {
        'MSE': mean_squared_error(y, y_pred),
        'RMSE': root_mean_squared_error(y, y_pred),
        'R2': r2_score(y, y_pred),
        'MAPE': mean_absolute_percentage_error(y, y_pred),
        'MAE': mean_absolute_error(y, y_pred)
    }
    return results_dict

def plot_circuit_with_metrics(feature_map, parameter_binds, metrics, metric_name='F'):
   
    qc = feature_map.assign_parameters(parameter_binds).decompose()

    num_qubits = qc.num_qubits
    num_gates = len(qc.data)

    if num_gates != len(metrics):
        raise ValueError("The number of gates its not equal to the number of metrics provided.")

    y_gap = 1.5
    box_width, box_height = 0.6, 0.6

    def y_ofset(q):
        return -y_gap * q
    
    
    figsize = (max(6.0, 1.15 * num_gates + 2), max(3.0, y_gap * num_qubits + 1.8))
    fig, ax = plt.subplots(figsize=figsize)

    for q in range(num_qubits):
        y=y_ofset(q)
        ax.hlines(y, 0, num_gates, color='black', linewidth=1)
        ax.text(-0.5, y, f'$q_{{{q}}}$', fontsize=10, ha='right', va='center')

    for i, instruction in enumerate(qc.data):
        gate = instruction.operation
        qubits = instruction.qubits
        label = gate.name.upper()

        qubit_index = [qubit._index for qubit in qubits]
        
        x_pos = i

        ax.text(x_pos, y_ofset(0) + box_height / 2 + 0.22, str(i), ha='center', va='bottom',
                fontsize=7, color='gray')

        m_val = metrics[i]['M']
        m_text = f"{metric_name}={m_val:.3f}"

        def draw_box(x, y):
            rect = mpatches.Rectangle((x - box_width / 2, y - box_height / 2), box_width, box_height,
                                      linewidth=1, edgecolor='black', facecolor='#e3f2fd', zorder=2)
            ax.add_patch(rect)

        if len(qubit_index) == 1:
            q = qubit_index[0]
            y = y_ofset(q)
            draw_box(x_pos, y)
            ax.text(x_pos, y, label, ha='center', va='center', fontsize=10, zorder=3)
            ax.text(x_pos, y - box_height / 2 - 0.1, m_text, ha='center', va='top', fontsize=8, zorder=3)
        elif len(qubit_index) == 2:
            q1, q2 = qubit_index
            y1, y2 = y_ofset(q1), y_ofset(q2)
            ax.plot([x_pos, x_pos], [y1, y2], color='black', linewidth=1, zorder=1)

            if gate.name in ('cx', 'cnot'):
                r = box_width / 2.6
                ax.add_patch(mpatches.Circle((x_pos, y1), 0.1, facecolor='black', zorder=3))
                ax.add_patch(mpatches.Circle((x_pos, y2), r, facecolor='white', edgecolor='black', linewidth=1, zorder=3))
                ax.plot([x_pos, x_pos], [y2 - r, y2 + r], color='black', linewidth=1, zorder=4)
                ax.plot([x_pos - r, x_pos + r], [y2, y2], color='black', linewidth=1, zorder=4)
            else:
                draw_box(x_pos, y1)
                draw_box(x_pos, y2)
                ax.text(x_pos, y1, label, ha='center', va='center', fontsize=10, zorder=3)
                ax.text(x_pos, y2, label, ha='center', va='center', fontsize=10, zorder=3)
            y_text = min(y1, y2) - box_width / 2.6 - 0.16
            ax.text(x_pos, y_text, m_text, ha='center', va='top', fontsize=8, zorder=3)

        else:
            ys = [y_ofset(q) for q in qubit_index]
            ax.plot([x_pos, x_pos], [min(ys), max(ys)], color='black', lw=1.2, zorder=2)
            for y in ys:
                draw_box(x_pos, y)
                ax.text(x_pos, y, label, ha='center', va='center', fontsize=10, zorder=3)
            ax.text(x_pos, min(ys) - box_width / 2.6 - 0.16, m_text, ha='center', va='top',
                    fontsize=8, zorder=3)
            

    ax.set_xlim(-1.4, num_gates - 0.4)
    ax.set_ylim(y_ofset(num_qubits - 1) - 0.9, y_ofset(0) + 0.95)
    ax.set_aspect('equal')
    ax.axis('off')
    ax.set_title(f"Feature map circuit \u2014 {metric_name} per gate", fontsize=12)

    fig.tight_layout()
    

    return fig_to_png_bytes(fig, dpi=300)

def fig_to_png_bytes(fig, dpi=150):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()

def plot_circuit(circuit):
    fig = circuit.draw(output="mpl")
    return fig_to_png_bytes(fig, dpi=150)

def create_feature_map(num_qubits):
    """
    Create a ZZFeatureMap with a specified number of qubits and linear entanglement.
    """
    return ZZFeatureMap(feature_dimension=num_qubits, reps=1, entanglement='linear', parameter_prefix="theta")



def is_data_parameter(p):
    return isinstance(p, ParameterExpression)

def remove_low_M_gates(feature_map, metrics, M_threshold=0.6):
    fm = feature_map.decompose()
    new_circuit = QuantumCircuit(fm.num_qubits)

    keep_positions = set(m["position"] for m in metrics if m["M"] >= M_threshold)

    for idx, inst in enumerate(fm.data):
        op = inst.operation
        if any(is_data_parameter(p) for p in getattr(op, "params", [])):
            new_circuit.append(op, inst.qubits)
        else:
            if idx in keep_positions:
                new_circuit.append(op, inst.qubits)

    return new_circuit


def QSVRTrain(X_train, y_train, X_val, y_val, feature_map, config):
    """
    Train a QSVR model using the Fidelity Quantum Kernel with a specified feature map.
    """
    qkernel = FidelityQuantumKernel(feature_map=feature_map)

    qsvr = QSVR(quantum_kernel=qkernel, C=config['C'], epsilon=config['epsilon'],
                tol=config.get('tol', 1e-3), max_iter=config.get('max_iter', -1))

    train_features, val_features = X_train.to_numpy(), X_val.to_numpy()
    train_labels, val_labels = y_train.to_numpy(), y_val.to_numpy()

    assert feature_map.num_qubits == train_features.shape[1], \
        "Mismatch between the feature map qubits and input data features."

    start_time = time.time()
    qsvr.fit(train_features, train_labels)
    training_time = time.time() - start_time

    print(f'QSVR training time: {training_time}')

    start_time = time.time()
    val_predictions = qsvr.predict(val_features)
    validation_score = mean_absolute_error(val_labels, val_predictions)
    validation_time = time.time() - start_time

    print(f'QSVR validation time: {validation_time}')
    print(f"QSVR regression validation score: {validation_score}")

    return qsvr, validation_score, training_time + validation_time


def QSVRTest(model, X_test, y_test, scaler_y):
    """
    Test the trained QSVRTest model on a test dataset.
    """

    test_features = X_test.to_numpy()
    test_labels = y_test.to_numpy().reshape(-1, 1)

    start_time = time.time()
    QSVR_predictions = model.predict(test_features)
    testing_time = time.time() - start_time

    if scaler_y is not None:
        QSVR_predictions = scaler_y.inverse_transform(QSVR_predictions.reshape(-1, 1)).ravel()
        test_labels = scaler_y.inverse_transform(test_labels)

    metrics = results(test_labels, QSVR_predictions)

    print(f'QSVR testing time: {testing_time}')
    print(f"QSVR regression test metrics: {metrics}")

    return metrics, testing_time


def QNNTrain(X_train, y_train, X_val, y_val, feature_map, config):
    """
    Train a QNN model using the Fidelity Quantum Kernel with a specified feature map.
    """

    train_features, val_features = X_train.to_numpy(), X_val.to_numpy()
    train_labels, val_labels = y_train.to_numpy().reshape(-1, 1) , y_val.to_numpy().reshape(-1, 1)

    num_qubits = feature_map.num_qubits

    ansatz = EfficientSU2(num_qubits=num_qubits, reps=config['reps'])
    qc = feature_map.compose(ansatz)

    cadena_pauli = "I" * (num_qubits - 1) + "Z" 
    observable = SparsePauliOp.from_list([(cadena_pauli, 1)])

    rng = np.random.default_rng(42)
    puntos_iniciales = rng.uniform(-np.pi, np.pi, ansatz.num_parameters)

    qnn = EstimatorQNN(circuit=qc, input_params=feature_map.parameters, observables=observable, weight_params=ansatz.parameters)

    if config['optimizador'] == 'SPSA':
        QNNR = NeuralNetworkRegressor(neural_network=qnn, 
                optimizer=SPSA(maxiter=config['max_iter'], learning_rate=config['learning_rate'], 
                perturbation=config['perturbacion']), initial_point=puntos_iniciales, loss='absolute_error', warm_start=False)
    elif config['optimizador'] == 'COBYLA':
        QNNR = NeuralNetworkRegressor(neural_network=qnn,
                optimizer=COBYLA(maxiter=config['max_iter'], tol=config['tol'],
                rhobeg=config['rhobeg']), initial_point=puntos_iniciales, loss='absolute_error', warm_start=False)
    elif config['optimizador'] == 'L_BFGS_B':
        QNNR = NeuralNetworkRegressor(neural_network=qnn,
                optimizer=L_BFGS_B(maxiter=config['max_iter'], ftol=config['ftol']),
                initial_point=puntos_iniciales, loss='absolute_error', warm_start=False)

    assert feature_map.num_qubits == train_features.shape[1], \
        "Mismatch between the feature map qubits and input data features."

    start_time = time.time()
    QNNR.fit(train_features, train_labels)
    training_time = time.time() - start_time

    print(f'QNN training time: {training_time}')

    start_time = time.time()
    val_predictions = QNNR.predict(val_features)
    validation_score = mean_absolute_error(val_labels, val_predictions)
    validation_time = time.time() - start_time

    print(f'QNN validation time: {validation_time}')
    print(f"QNN regression validation score: {validation_score}")

    return QNNR, validation_score, training_time + validation_time


def QNNTest(model, X_test, y_test, scaler_y):
    """
    Test the trained QNN model on a test dataset.
    """

    test_features = X_test.to_numpy()
    test_labels = y_test.to_numpy().reshape(-1, 1) 

    start_time = time.time()
    QNN_predictions = model.predict(test_features)
    testing_time = time.time() - start_time

    if scaler_y is not None:
        QNN_predictions = scaler_y.inverse_transform(QNN_predictions.reshape(-1, 1)).ravel()
        test_labels = scaler_y.inverse_transform(test_labels)

    metrics = results(test_labels, QNN_predictions)

    print(f'QNN testing time: {testing_time}')
    print(f"QNN regression test metrics: {metrics}")

    return metrics, testing_time

