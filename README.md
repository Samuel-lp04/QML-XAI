# QML-XAI

**A web platform for training and explaining quantum machine learning models.**

QML-XAI is an open-source web application that lets you train quantum machine learning (QML) regression models on your own data **without writing code**, and see which gates of the quantum circuit matter. After training, it computes the **Gate Significance Index (GSI)** of every gate, removes the least significant gates, retrains the reduced circuits and compares them with the original circuit in terms of accuracy and training time.

> **Note:** the user interface is currently in Spanish.

---

## Table of contents

- [Features](#features)
- [How it works](#how-it-works)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Dataset format](#dataset-format)
- [Reproducing the experiments of the paper](#reproducing-the-experiments-of-the-paper)
- [Project structure](#project-structure)
- [Technologies](#technologies)
- [License](#license)
- [Contact](#contact)

---

## Features

- **Two quantum regression models**
  - **QNN** (quantum neural network): `ZZFeatureMap` + `EfficientSU2` ansatz, trained with SPSA, COBYLA or L-BFGS-B.
  - **QSVR** (quantum support vector regressor) with a fidelity quantum kernel.
- **Explainability with the GSI.** Each project uses one of two approaches:
  - **Fidelity (F):** the fidelity between the quantum state before and after each gate.
  - **Entanglement (E):** the normalised entanglement entropy after each gate.
- **Automatic gate removal.** Reduced circuits are generated for a range of thresholds and retrained with the same configuration.
- **Model comparison.** The base circuit is compared with the most accurate and the fastest reduced circuits using MSE, RMSE, MAE, MAPE, R² and training/test times.
- **Circuit plots** with the GSI value of each gate.
- **Background training.** Trainings run in a separate thread, so the application stays usable while the simulation runs. Each project shows its status: *No entrenado*, *Entrenando*, *Entrenado* or *Error*.
- **Export.** Results can be downloaded as a ZIP file with the test metrics, the table of all trained circuits, the model configuration and the circuit plots.
- **User management.** Registration, login and password recovery by e-mail. Passwords are stored hashed, and each user only has access to their own datasets and projects.
- **Reproducibility.** A fixed random seed (`42`) is used for data splitting, simulation and initial parameters.

---

## How it works

1. **Preprocessing.** The dataset is split into training (60%), validation (20%) and test (20%) sets. The scalers are fitted on the training set only: input features are scaled to `[0, π]` (angle encoding) and the target is standardised.
2. **Feature map.** A `ZZFeatureMap` (1 repetition, linear entanglement) is built with one qubit per input feature.
3. **GSI computation.** The gates of the feature map are applied one by one to the state encoding the first training sample, and a value `M` is computed for each gate with the selected approach (F or E).
4. **Gate removal.** Thresholds go from the minimum to the maximum value of `M` in steps of `0.02`, rounded to four decimals. The circuit obtained with the first threshold is the **base circuit**. With the fidelity approach, rounding can place the first threshold slightly above the minimum value of `M`, so the base circuit can lack the gate with the lowest fidelity; this is why the base results of F and E can differ slightly. For each threshold, the gates with `M` below the threshold are removed. Gates parameterised by the input data are **always kept**, so no input information is lost. Thresholds that give the same number of gates as the previous one are skipped.
5. **Training.** The base circuit and every reduced circuit are trained with the same configuration and evaluated on the **validation set** (MAE). The test set is not used for any decision.
6. **Selection** (on the validation set):
   - **Best MAE:** the reduced circuit with the lowest validation MAE.
   - **Best time:** the fastest reduced circuit whose validation MAE is at most 15% worse than that of the base circuit.
7. **Test.** The base, best-MAE and best-time circuits are evaluated on the test set, and all the results are stored in the database.

---

## Requirements

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose (included in Docker Desktop on Windows and macOS).
- Free ports **5000** (web application) and **3307** (MySQL).
- *(Optional, only for password recovery)* A Gmail account with 2-step verification enabled, to generate an [app password](https://myaccount.google.com/apppasswords).

---

## Installation

**1. Clone the repository**

```bash
git clone https://github.com/Samuel-lp04/QML-XAI.git
cd QML-XAI
```

**2. Create the configuration file**

```bash
cp .env.example .env
```

Edit `.env` and set at least:

| Variable | Description |
|---|---|
| `MYSQL_ROOT_PASSWORD`, `MYSQL_DATABASE`, `MYSQL_USER`, `MYSQL_PASSWORD` | Database credentials. The example values work for local use; change them if the service will be exposed. |
| `SECRET_KEY` | Secret key used by Flask to sign sessions and password-reset links. Use a long random string. |
| `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_DEFAULT_SENDER` | Gmail account used to send password-recovery e-mails. `MAIL_PASSWORD` is a Gmail **app password**, not your normal password. |
| `MAX_UPLOAD_MB` *(optional)* | Maximum dataset size in MB (default `16`). |
| `MAX_FEATURES` *(optional)* | Maximum number of input features, i.e. qubits (default `10`). |

> The `.env` file contains secrets and is excluded from version control. Never commit it.

**3. Build and start the containers**

```bash
docker compose up -d --build
```

This builds the web application image, starts a MySQL 8.0 container with a persistent volume, creates the database schema on the first start (`tfg.sql`) and starts the web application once the database is ready.

**4. Open the application**

Go to **http://localhost:5000** in your browser.

**Stopping and restarting**

```bash
docker compose stop      # stop the containers
docker compose up -d     # start them again
docker compose down      # stop and remove the containers (the data volume is kept)
```

---

## Usage

1. **Register** and log in.
2. **Upload a dataset** in the *Datasets* section (see [Dataset format](#dataset-format)).
3. **Create a project** in *Crear proyecto*:
   - Give it a name and select a dataset.
   - Create a new model or reuse a saved one, and choose its type:
     - **QNN:** number of ansatz repetitions and optimiser (SPSA, COBYLA or L-BFGS-B) with its hyperparameters.
     - **QSVR:** `C`, `epsilon`, `tol` and `max_iter`.
   - Choose the **GSI approach**: *Fidelity* or *Entanglement*.
4. **Train** the project from *Proyectos*. The status changes to *Entrenando* and you can keep using the application. Depending on the dataset and the model, training takes from seconds to several minutes.
5. When the status is *Entrenado*, open **Resultados** to see:
   - the test metrics and times of the base, best-MAE and best-time circuits,
   - the table of all the circuits trained for each threshold,
   - the circuit plots with the GSI value of each gate.
6. Download the results as a ZIP file if needed.

> **Reproducibility tip:** the random seed is global, so train **one project at a time** if you want to obtain exactly the same results in every run.

---

## Dataset format

- File types: `.csv`, `.tsv` or `.txt`. The separator (comma, semicolon or tab) is detected automatically.
- The first row must contain the column names.
- **The last column is the target variable**; all the other columns are input features.
- All columns must be **numeric**, with **no missing values**.
- At least **10 rows** and at most **`MAX_FEATURES` features** (10 by default), since each feature is encoded in one qubit.

Example:

```csv
feature_1,feature_2,feature_3,target
0.52,12.0,3.1,105.2
0.48,10.5,2.9,98.7
...
```

---

## Reproducing the experiments of the paper

The experiments use four regression datasets from the [Penn Machine Learning Benchmarks (PMLB)](https://github.com/EpistasisLab/pmlb): `230_machine_cpu`, `547_no2`, `627_fri_c2_500_10` and `1096_FacultySalaries`.

The script `experiments/run_experiments.py` runs exactly the same pipeline as the web application, without the interface and without Docker:

```bash
pip install -r requirements.txt
python experiments/run_experiments.py
```

It downloads the datasets from PMLB, trains every model in `experiments/configs.json` with both GSI approaches (one run after another) and saves:

- `experiments/results/metrics.csv`: test metrics and times of the base, best-MAE and best-time circuits;
- `experiments/results/circuits.csv`: every circuit trained for each threshold (number of gates, validation MAE, time and selection).

Useful options:

```bash
python experiments/run_experiments.py --datasets 230_machine_cpu --models QSVR   # a single dataset and model
python experiments/run_experiments.py --data-dir my_csvs                          # local CSV files instead of PMLB
python experiments/run_experiments.py --configs experiments/configs_example.json  # quick test with small settings
```

To export the datasets as CSV files and upload them to the web application instead:

```python
from pmlb import fetch_data

for name in ["230_machine_cpu", "547_no2", "627_fri_c2_500_10", "1096_FacultySalaries"]:
    df = fetch_data(name)
    df = df[[c for c in df.columns if c != "target"] + ["target"]]  # target as last column
    df.to_csv(f"{name}.csv", index=False)
```

---

## Project structure

```
QML-XAI/
├── app.py                       # Flask application: routes, authentication, database models, background training
├── entrenamiento.py             # Training pipeline: preprocessing, GSI, gate removal, selection and test
├── GSI.py                       # GSI-F / GSI-E, gate removal, QNN and QSVR training and testing, circuit plots
├── experiments/
│   ├── run_experiments.py       # Reproduces the experiments of the paper without the web interface
│   ├── configs.json             # Model configurations used in the paper
│   └── configs_example.json     # Small configuration for a quick test
├── templates/                   # Jinja2 templates (HTML pages)
├── static/                      # CSS, JavaScript and images
├── tfg.sql                      # Database schema, loaded automatically on the first start
├── requirements.txt             # Python dependencies
├── Dockerfile                   # Web application image (Python 3.12 + gunicorn)
├── docker-compose.yml           # Web application + MySQL 8.0
├── .env.example                 # Configuration template
└── LICENSE
```

---

## Technologies

- **Backend:** Python 3.12, Flask, Flask-Login, Flask-WTF, Flask-Mail, SQLAlchemy, gunicorn
- **Quantum computing:** Qiskit, Qiskit Machine Learning, Qiskit Algorithms
- **Data and evaluation:** pandas, NumPy, scikit-learn, matplotlib
- **Frontend:** Jinja2, Bootstrap, JavaScript
- **Database:** MySQL 8.0
- **Deployment:** Docker, Docker Compose

All the computations run on Qiskit's classical simulator; no access to quantum hardware is needed.

---

## License

This project is distributed under the MIT License. See [`LICENSE`](LICENSE) for details.

---

## Contact

Samuel López-Pérez · Universidad Pablo de Olavide, Seville, Spain
For questions or bug reports, please open an [issue](https://github.com/Samuel-lp04/QML-XAI/issues) or write to **samuel.lopez.perez2004@gmail.com**.
