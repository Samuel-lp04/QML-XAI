import os
import re
import io
import csv
import zipfile
import threading
import entrenamiento
from flask import Flask, Response, json, request, render_template, redirect, url_for, flash, send_file
from werkzeug.security import check_password_hash, generate_password_hash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.mysql import MEDIUMBLOB
from sqlalchemy.exc import IntegrityError
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect, CSRFError
from datetime import date
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer, BadData
from dotenv import load_dotenv
import traceback

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

usuarioBd  = os.getenv('MYSQL_USER')
claveBd    = os.getenv('MYSQL_PASSWORD')
servidorBd = os.getenv('DATABASE_HOST')
nombreBd   = os.getenv('MYSQL_DATABASE')

app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://{usuarioBd}:{claveBd}@{servidorBd}/{nombreBd}'
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True, 'pool_recycle': 280}

# Tamaño máximo de las subidas (por defecto 16 MB). Las peticiones mayores reciben un 413.
app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_UPLOAD_MB', '16')) * 1024 * 1024

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER')

db = SQLAlchemy(app)
mail = Mail(app)
csrf = CSRFProtect(app)
s = URLSafeTimedSerializer(app.config['SECRET_KEY'])

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

MIN_LONGITUD_PASSWORD = 8
LONGITUD_NOMBRE = 50  # longitud de las columnas varchar(50) de nombres
EMAIL_REGEX = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


class User(UserMixin, db.Model):
    __tablename__ = 'usuario'
    idUsuario = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)

    def get_id(self):
        return str(self.idUsuario)

class Modelo(db.Model):
    __tablename__ = 'modelo'
    idModelo = db.Column(db.Integer, primary_key=True, autoincrement=True)
    idUsuario = db.Column(db.Integer, db.ForeignKey('usuario.idUsuario'), nullable=False)
    nombreModelo = db.Column(db.String(50), nullable=False)
    ficheroConf = db.Column(db.Text, nullable=False)

class Dataset(db.Model):
    __tablename__ = 'datasets'
    idDatasets = db.Column(db.Integer, primary_key=True, autoincrement=True)
    idUsuario = db.Column(db.Integer, db.ForeignKey('usuario.idUsuario'), nullable=False)
    fichero = db.Column(db.LargeBinary, nullable=False)
    nombreFichero = db.Column(db.String(50), nullable=False)

class Proyecto(db.Model):
    __tablename__ = 'proyectos'
    idProyecto = db.Column(db.Integer, primary_key=True, autoincrement=True)
    idUsuario = db.Column(db.Integer, db.ForeignKey('usuario.idUsuario'), nullable=False)
    idModelo = db.Column(db.Integer, db.ForeignKey('modelo.idModelo'), nullable=False)
    idDatasets = db.Column(db.Integer, db.ForeignKey('datasets.idDatasets'), nullable=False)
    nombreProyecto = db.Column(db.String(50), nullable=False)
    fecha = db.Column(db.Date, nullable=False)
    estado = db.Column(db.String(30), nullable=False)
    all_circuits = db.Column(db.Text, nullable=True)

    modelo_info = db.relationship('Modelo', backref='proyectos_asociados')
    dataset_info = db.relationship('Dataset', backref='proyectos_asociados')

class Resultado(db.Model):
    __tablename__ = 'resultados'
    idResultado = db.Column(db.Integer, primary_key=True, autoincrement=True)
    idProyecto = db.Column(db.Integer, db.ForeignKey('proyectos.idProyecto'), nullable=False)
    tipoModelo = db.Column(db.String(20), nullable=False)
    MSE = db.Column(db.Float, nullable=False)
    RMSE = db.Column(db.Float, nullable=False)
    MAE = db.Column(db.Float, nullable=False)
    MAPE = db.Column(db.Float, nullable=False)
    R2 = db.Column(db.Float, nullable=False)
    trainingTime = db.Column(db.Float, nullable=False)
    testingTime = db.Column(db.Float, nullable=False)
    grafica = db.Column(MEDIUMBLOB, nullable=True)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ---------------------------------------------------------------------------
# Manejadores de error
# ---------------------------------------------------------------------------

@app.errorhandler(CSRFError)
def manejar_csrf(e):
    flash('La sesión del formulario ha caducado. Vuelve a intentarlo.', 'error')
    return redirect(request.referrer or url_for('home'))

@app.errorhandler(413)
def fichero_demasiado_grande(e):
    flash(f"El archivo supera el tamaño máximo permitido ({app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)} MB).", 'error')
    return redirect(request.referrer or url_for('home'))


# ---------------------------------------------------------------------------
# Recuperación al arrancar: los entrenamientos que estaban en curso cuando se
# paró la aplicación ya no existen (los hilos mueren con el proceso).
# NOTA: esto asume un único proceso de gunicorn (--workers 1, como en el Dockerfile).
# ---------------------------------------------------------------------------

def _recuperar_entrenamientos_interrumpidos():
    try:
        with app.app_context():
            n = Proyecto.query.filter_by(estado='Entrenando').update({'estado': 'Error'})
            db.session.commit()
            if n:
                print(f"{n} proyecto(s) en 'Entrenando' marcados como 'Error' tras reiniciar la aplicación.")
    except Exception as e:
        print(f"No se pudieron revisar los entrenamientos interrumpidos: {e}")

_recuperar_entrenamientos_interrumpidos()


# ---------------------------------------------------------------------------
# Autenticación
# ---------------------------------------------------------------------------

def _sello_password(user):
    """Fragmento del hash actual: al cambiar la contraseña, el token deja de valer."""
    return user.password_hash[-16:]

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('home'))
        else:
            flash('Usuario o contraseña incorrectos', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        email = request.form.get('email', '').strip().lower()

        errores = []
        if not username or len(username) > 50:
            errores.append('El nombre de usuario es obligatorio y debe tener como máximo 50 caracteres.')
        if not EMAIL_REGEX.match(email) or len(email) > 150:
            errores.append('Introduce un correo electrónico válido.')
        if len(password) < MIN_LONGITUD_PASSWORD:
            errores.append(f'La contraseña debe tener al menos {MIN_LONGITUD_PASSWORD} caracteres.')
        if not errores and User.query.filter_by(username=username).first():
            errores.append('El usuario ya existe.')
        if not errores and User.query.filter_by(email=email).first():
            errores.append('Ya existe una cuenta con ese correo electrónico.')

        if errores:
            for e in errores:
                flash(e, 'error')
            return redirect(url_for('register'))

        new_user = User(username=username, password_hash=generate_password_hash(password), email=email)
        db.session.add(new_user)
        try:
            db.session.commit()
        except IntegrityError:
            # Carrera entre dos registros simultáneos con el mismo usuario/correo
            db.session.rollback()
            flash('El usuario o el correo ya están registrados.', 'error')
            return redirect(url_for('register'))
        flash('Cuenta creada. Ya puedes iniciar sesión.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.query.filter_by(email=email).first()

        if user:
            token = s.dumps({'email': user.email, 'sello': _sello_password(user)}, salt='email-confirm')
            link = url_for('confirm_reset', token=token, _external=True)

            msg = Message('Recuperación de contraseña - QML-XAI', recipients=[user.email])
            msg.body = f'Haz clic aquí para restablecer tu contraseña: {link}\nExpira en 30 minutos.'
            try:
                mail.send(msg)
            except Exception:
                # No se revela al usuario si el correo existe; solo se registra el fallo.
                traceback.print_exc()

        flash('Si el correo existe, recibirás instrucciones en breve.', 'info')
        return redirect(url_for('login'))
    return render_template('reset_password.html')

@app.route('/confirm-reset/<token>', methods=['GET', 'POST'])
def confirm_reset(token):
    try:
        datos = s.loads(token, salt='email-confirm', max_age=1800)
        email, sello = datos['email'], datos['sello']
    except (BadData, KeyError, TypeError):
        flash('El enlace es inválido o ha expirado.', 'error')
        return redirect(url_for('reset_password'))

    user = User.query.filter_by(email=email).first()
    # Si la contraseña ya se cambió (con este enlace u otro), el sello no coincide.
    if not user or _sello_password(user) != sello:
        flash('El enlace es inválido o ya se ha utilizado.', 'error')
        return redirect(url_for('reset_password'))

    if request.method == 'POST':
        nueva_pass = request.form.get('password', '')
        if len(nueva_pass) < MIN_LONGITUD_PASSWORD:
            flash(f'La contraseña debe tener al menos {MIN_LONGITUD_PASSWORD} caracteres.', 'error')
            return redirect(url_for('confirm_reset', token=token))
        user.password_hash = generate_password_hash(nueva_pass)
        db.session.commit()
        flash('Contraseña actualizada con éxito.', 'success')
        return redirect(url_for('login'))

    return render_template('new_password.html')


# ---------------------------------------------------------------------------
# Páginas
# ---------------------------------------------------------------------------

@app.route('/')
@app.route('/home')
def home():
    if current_user.is_authenticated:
        proyectos_totales = Proyecto.query.filter_by(idUsuario=current_user.idUsuario).count()
        proyectos_recientes = Proyecto.query.filter_by(idUsuario=current_user.idUsuario).order_by(Proyecto.fecha.desc()).limit(3).all()
    else:
        proyectos_totales = 0
        proyectos_recientes = []

    return render_template('home.html', proyectos_totales=proyectos_totales, proyectos_recientes=proyectos_recientes)

@app.route('/proyectos')
@login_required
def proyectos():
    page = request.args.get('page', 1, type=int)
    proyectos_paginados = Proyecto.query.filter_by(idUsuario=current_user.idUsuario)\
                                        .order_by(Proyecto.fecha.desc())\
                                        .paginate(page=page, per_page=5, error_out=False)
    return render_template('proyectos.html', proyectos_paginados=proyectos_paginados)


# ---------------------------------------------------------------------------
# Creación de proyectos
# ---------------------------------------------------------------------------

def _leer_numero(nombre, tipo, errores, minimo=None, estricto=False):
    """Lee un campo numérico del formulario. Añade un error si falta o no es válido."""
    valor = request.form.get(nombre, '').strip()
    try:
        numero = tipo(valor)
    except (TypeError, ValueError):
        errores.append(f'El campo "{nombre}" es obligatorio y debe ser un número válido.')
        return None
    if minimo is not None and (numero <= minimo if estricto else numero < minimo):
        errores.append(f'El campo "{nombre}" debe ser {"mayor que" if estricto else "mayor o igual que"} {minimo}.')
        return None
    return numero

def _leer_id(nombre):
    try:
        return int(request.form.get(nombre, ''))
    except ValueError:
        return None

def _config_desde_formulario(errores):
    """Construye la configuración de un modelo nuevo validando todos los campos."""
    GSI = request.form.get('GSI')
    if GSI not in ('F', 'E'):
        errores.append('Debes seleccionar un Gate Significance Index válido (Fidelity o Entanglement).')

    tipo_modelo = request.form.get('tipoModelo')
    if tipo_modelo == 'QSVR':
        config = {
            'tipo': 'QSVR',
            'GSI': GSI,
            'C': _leer_numero('C_qsvr', float, errores, 0, estricto=True),
            'epsilon': _leer_numero('epsilon_qsvr', float, errores, 0),
            'max_iter': _leer_numero('max_iter_qsvr', int, errores, -1),  # -1 = sin límite (sklearn)
            'tol': _leer_numero('tol_qsvr', float, errores, 0, estricto=True),
        }
    elif tipo_modelo == 'QNN':
        opt = request.form.get('optimizador')
        config = {
            'tipo': 'QNN',
            'GSI': GSI,
            'reps': _leer_numero('reps', int, errores, 1),
            'optimizador': opt,
        }
        if opt == 'L_BFGS_B':
            config.update({'max_iter': _leer_numero('max_iter_lbfgs', int, errores, 1),
                           'ftol': _leer_numero('ftol_lbfgs', float, errores, 0, estricto=True)})
        elif opt == 'COBYLA':
            config.update({'max_iter': _leer_numero('max_iter_cobyla', int, errores, 1),
                           'rhobeg': _leer_numero('rhobeg_cobyla', float, errores, 0, estricto=True),
                           'tol': _leer_numero('tol_cobyla', float, errores, 0, estricto=True)})
        elif opt == 'SPSA':
            config.update({'max_iter': _leer_numero('max_iter_spsa', int, errores, 1),
                           'learning_rate': _leer_numero('learning_rate_spsa', float, errores, 0, estricto=True),
                           'perturbacion': _leer_numero('perturbacion_spsa', float, errores, 0, estricto=True)})
        else:
            errores.append('Debes seleccionar un optimizador (L_BFGS_B, COBYLA o SPSA).')
    else:
        errores.append('Debes seleccionar el tipo de modelo (QNN o QSVR).')
        config = None
    return config

def _validar_fichero_dataset(archivo, errores):
    """Lee y valida un fichero subido. Devuelve (bytes, nombre) o (None, None)."""
    contenido = archivo.read()
    try:
        entrenamiento.leer_dataset(contenido)
    except ValueError as e:
        errores.append(f'Dataset no válido: {e}')
        return None, None
    nombre = os.path.splitext(archivo.filename)[0][:LONGITUD_NOMBRE] or 'dataset'
    return contenido, nombre

@app.route('/crear_proyecto', methods=['GET', 'POST'])
@login_required
def crear_proyecto():
    if request.method == 'POST':
        errores = []

        nombre = request.form.get('nombre_proyecto', '').strip()
        if not nombre or len(nombre) > LONGITUD_NOMBRE:
            errores.append(f'El nombre del proyecto es obligatorio (máximo {LONGITUD_NOMBRE} caracteres).')

        # --- Modelo ---
        modelo_tipo = request.form.get('modelo')
        nuevo_modelo = None
        modelo_existente = None
        if modelo_tipo == 'nuevo':
            nombre_modelo = request.form.get('nombre_modelo', '').strip()
            if not nombre_modelo or len(nombre_modelo) > LONGITUD_NOMBRE:
                errores.append(f'El nombre del modelo es obligatorio (máximo {LONGITUD_NOMBRE} caracteres).')
            config = _config_desde_formulario(errores)
            if not errores:
                nuevo_modelo = Modelo(idUsuario=current_user.idUsuario, nombreModelo=nombre_modelo,
                                      ficheroConf=json.dumps(config))
        elif modelo_tipo == 'usado':
            id_modelo = _leer_id('modelo_usado')
            modelo_existente = Modelo.query.filter_by(idModelo=id_modelo, idUsuario=current_user.idUsuario).first() \
                if id_modelo is not None else None
            if not modelo_existente:
                errores.append('Debes seleccionar uno de tus modelos guardados.')
        else:
            errores.append('Debes seleccionar un tipo de modelo (nuevo o usado).')

        # --- Dataset ---
        archivo = request.files.get('dataset_nuevo')
        nuevo_dataset = None
        dataset_existente = None
        if archivo and archivo.filename:
            contenido, nombre_fichero = _validar_fichero_dataset(archivo, errores)
            if contenido is not None:
                nuevo_dataset = Dataset(idUsuario=current_user.idUsuario, fichero=contenido,
                                        nombreFichero=nombre_fichero)
        else:
            id_dataset = _leer_id('dataset_existente')
            if id_dataset is not None:
                dataset_existente = db.session.query(Dataset.idDatasets).filter_by(
                    idDatasets=id_dataset, idUsuario=current_user.idUsuario).first()
            if not dataset_existente:
                errores.append('Debes seleccionar un dataset de la nube o subir uno nuevo.')

        if errores:
            for e in errores:
                flash(e, 'error')
            return redirect(url_for('crear_proyecto'))

        # Todo validado: se guarda en una única transacción
        if nuevo_modelo:
            db.session.add(nuevo_modelo)
        if nuevo_dataset:
            db.session.add(nuevo_dataset)
        db.session.flush()

        nuevo_p = Proyecto(
            idUsuario=current_user.idUsuario,
            idModelo=nuevo_modelo.idModelo if nuevo_modelo else modelo_existente.idModelo,
            idDatasets=nuevo_dataset.idDatasets if nuevo_dataset else dataset_existente.idDatasets,
            nombreProyecto=nombre,
            fecha=date.today(),
            estado='No entrenado'
        )
        db.session.add(nuevo_p)
        db.session.commit()
        flash('Proyecto creado.', 'success')
        return redirect(url_for('proyectos'))

    # Solo se piden id y nombre (sin cargar los ficheros de los datasets)
    modelos = db.session.query(Modelo.idModelo, Modelo.nombreModelo)\
                        .filter_by(idUsuario=current_user.idUsuario).order_by(Modelo.nombreModelo).all()
    datasets = db.session.query(Dataset.idDatasets, Dataset.nombreFichero)\
                         .filter_by(idUsuario=current_user.idUsuario).order_by(Dataset.nombreFichero).all()
    return render_template('crear_proyecto.html', modelos=modelos, datasets=datasets)


# ---------------------------------------------------------------------------
# Entrenamiento
# ---------------------------------------------------------------------------

def _entrenar_en_segundo_plano(proyecto_id, config, dataset_bytes):
    with app.app_context():
        try:
            resultados, all_circuits = entrenamiento.entrenamiento(dataset_bytes, config)

            Resultado.query.filter_by(idProyecto=proyecto_id).delete()

            for r in resultados:
                db.session.add(Resultado(
                    idProyecto=proyecto_id,
                    tipoModelo=r['tipo'],
                    MSE=r['MSE'],
                    RMSE=r['RMSE'],
                    MAE=r['MAE'],
                    MAPE=r['MAPE'],
                    R2=r['R2'],
                    trainingTime=r['trainingTime'],
                    testingTime=r['testingTime'],
                    grafica=r.get('grafica'),
                ))

            proyecto = db.session.get(Proyecto, proyecto_id)
            proyecto.estado = 'Entrenado'
            proyecto.all_circuits = json.dumps(all_circuits)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            traceback.print_exc()
            print(f"Error entrenando el proyecto {proyecto_id}: {e}")
            proyecto = db.session.get(Proyecto, proyecto_id)
            if proyecto:
                proyecto.estado = 'Error'
                db.session.commit()


@app.route('/entrenar_proyecto/<int:proyecto_id>', methods=['POST'])
@login_required
def entrenar_proyecto(proyecto_id):
    proyecto = Proyecto.query.filter_by(idProyecto=proyecto_id, idUsuario=current_user.idUsuario).first_or_404()

    if proyecto.estado != 'No entrenado':
        flash('Este proyecto no está listo para ser entrenado.', 'info')
        return redirect(url_for('proyectos'))

    modelo = db.session.get(Modelo, proyecto.idModelo)
    dataset = db.session.get(Dataset, proyecto.idDatasets)
    config = json.loads(modelo.ficheroConf)
    dataset = dataset.fichero

    proyecto.estado = 'Entrenando'
    db.session.commit()

    hilo = threading.Thread(
        target=_entrenar_en_segundo_plano,
        args=(proyecto.idProyecto, config, dataset),
        daemon=True
    )
    hilo.start()

    flash('Entrenamiento iniciado. Puede tardar varios minutos; recarga la página para ver el estado.', 'info')
    return redirect(url_for('proyectos'))


# ---------------------------------------------------------------------------
# Datasets y resultados
# ---------------------------------------------------------------------------

@app.route('/datasets')
@login_required
def datasets():
    # Solo id y nombre: no hace falta traer los ficheros de la base de datos
    datasets_paginados = db.session.query(Dataset.idDatasets, Dataset.nombreFichero)\
        .filter_by(idUsuario=current_user.idUsuario)\
        .order_by(Dataset.idDatasets.desc())\
        .paginate(page=request.args.get('page', 1, type=int), per_page=5, error_out=False)
    return render_template('dataset.html', datasets_paginados=datasets_paginados)

@app.route('/resultados/<int:proyecto_id>')
@login_required
def resultados(proyecto_id):
    proyecto = Proyecto.query.filter_by(
        idProyecto=proyecto_id, idUsuario=current_user.idUsuario
    ).first_or_404()
    if proyecto.estado != 'Entrenado' or not proyecto.all_circuits:
        flash('Este proyecto todavía no tiene resultados.', 'info')
        return redirect(url_for('proyectos'))
    filas = Resultado.query.filter_by(idProyecto=proyecto_id).all()
    resultados = {}
    for r in filas:
        resultados[r.tipoModelo] = r
    all_circuits = json.loads(proyecto.all_circuits)
    return render_template('resultados.html', proyecto=proyecto, resultados=resultados, all_circuits=all_circuits)

@app.route('/grafica/<int:id_resultado>')
@login_required
def grafica(id_resultado):
    r = Resultado.query.join(Proyecto).filter(
        Resultado.idResultado == id_resultado,
        Proyecto.idUsuario == current_user.idUsuario
    ).first_or_404()
    if not r.grafica:
        return '', 404
    if request.args.get('descargar'):
        return send_file(io.BytesIO(r.grafica), mimetype='image/png', as_attachment=True,
                         download_name=f'grafica_{_nombre_seguro(r.tipoModelo)}.png')
    return Response(r.grafica, mimetype='image/png')

@app.route('/eliminar_proyecto/<int:proyecto_id>', methods=['POST'])
@login_required
def eliminar_proyecto(proyecto_id):
    proyecto = Proyecto.query.filter_by(
        idProyecto=proyecto_id, idUsuario=current_user.idUsuario
    ).first_or_404()
    Resultado.query.filter_by(idProyecto=proyecto_id).delete()
    db.session.delete(proyecto)
    db.session.commit()

    flash('Proyecto eliminado.', 'success')
    return redirect(url_for('proyectos'))

# ---------------------------------------------------------------------------
# Descargas
# ---------------------------------------------------------------------------

def _nombre_seguro(nombre):
    """Nombre de fichero sin caracteres problemáticos."""
    return re.sub(r'[^\w.-]+', '_', nombre, flags=re.UNICODE).strip('_') or 'descarga'

def _csv_excel(cabecera, filas):
    """
    CSV pensado para abrirse con Excel en español: separador ';', coma decimal
    y BOM UTF-8 para que las tildes se vean bien.
    """
    def celda(v):
        if v is None:
            return ''
        if isinstance(v, float):
            return f'{v:.10g}'.replace('.', ',')
        if isinstance(v, (list, tuple)):
            return ', '.join(map(str, v))
        return v
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=';')
    w.writerow(cabecera)
    for fila in filas:
        w.writerow([celda(v) for v in fila])
    return '\ufeff' + buf.getvalue()

@app.route('/descargar_dataset/<int:dataset_id>')
@login_required
def descargar_dataset(dataset_id):
    dataset = Dataset.query.filter_by(idDatasets=dataset_id, idUsuario=current_user.idUsuario).first_or_404()
    # Al subirlo se guardó el nombre sin extensión: se deduce por el separador
    primera_linea = dataset.fichero.split(b'\n', 1)[0]
    extension = '.tsv' if b'\t' in primera_linea else '.csv'
    return send_file(io.BytesIO(dataset.fichero), mimetype='text/csv', as_attachment=True,
                     download_name=_nombre_seguro(dataset.nombreFichero) + extension)

@app.route('/descargar_resultados/<int:proyecto_id>')
@login_required
def descargar_resultados(proyecto_id):
    """ZIP con las métricas de test, la tabla de todos los circuitos, la configuración y las gráficas."""
    proyecto = Proyecto.query.filter_by(idProyecto=proyecto_id, idUsuario=current_user.idUsuario).first_or_404()
    if proyecto.estado != 'Entrenado' or not proyecto.all_circuits:
        flash('Este proyecto todavía no tiene resultados.', 'info')
        return redirect(url_for('proyectos'))

    filas = Resultado.query.filter_by(idProyecto=proyecto_id).all()
    circuitos = json.loads(proyecto.all_circuits).values()
    modelo = db.session.get(Modelo, proyecto.idModelo)

    metricas_csv = _csv_excel(
        ['Modelo', 'MSE', 'RMSE', 'MAE', 'MAPE', 'R2', 'Training time (s)', 'Testing time (s)'],
        [[r.tipoModelo, r.MSE, r.RMSE, r.MAE, r.MAPE, r.R2, r.trainingTime, r.testingTime] for r in filas])
    circuitos_csv = _csv_excel(
        ['Threshold', 'Puertas', 'MAE validacion', 'Tiempo (s)', 'Seleccion'],
        [[c.get('Threshold'), c.get('Num_Puertas'), c.get('Score'), c.get('Time'), c.get('seleccion', [])]
         for c in circuitos])

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('metricas_test.csv', metricas_csv)
        z.writestr('circuitos_entrenados.csv', circuitos_csv)
        z.writestr('configuracion_modelo.json', json.dumps(
            {'proyecto': proyecto.nombreProyecto, 'fecha': proyecto.fecha.isoformat(),
             'modelo': modelo.nombreModelo, 'configuracion': json.loads(modelo.ficheroConf)},
            indent=2, ensure_ascii=False))
        for r in filas:
            if r.grafica:
                z.writestr(f'graficas/{r.tipoModelo}.png', r.grafica)
    buf.seek(0)
    return send_file(buf, mimetype='application/zip', as_attachment=True,
                     download_name=f'resultados_{_nombre_seguro(proyecto.nombreProyecto)}.zip')

@app.route('/eliminar_dataset/<int:dataset_id>', methods=['POST'])
@login_required
def eliminar_dataset(dataset_id):
    dataset = Dataset.query.filter_by(
        idDatasets=dataset_id, idUsuario=current_user.idUsuario
    ).first_or_404()
    en_uso = Proyecto.query.filter_by(idDatasets=dataset_id).count()
    if en_uso:
        flash(f'No se puede eliminar: hay {en_uso} proyecto(s) que usan este dataset.', 'error')
        return redirect(url_for('datasets'))
    db.session.delete(dataset)
    db.session.commit()

    flash('Dataset eliminado.', 'success')
    return redirect(url_for('datasets'))

@app.route('/subir_dataset', methods=['POST'])
@login_required
def subir_dataset():
    archivo = request.files.get('dataset_nuevo')
    if not archivo or archivo.filename == '':
        flash('Selecciona un archivo antes de subirlo.', 'error')
        return redirect(url_for('datasets'))

    errores = []
    contenido, nombre = _validar_fichero_dataset(archivo, errores)
    if errores:
        for e in errores:
            flash(e, 'error')
        return redirect(url_for('datasets'))

    db.session.add(Dataset(idUsuario=current_user.idUsuario, fichero=contenido, nombreFichero=nombre))
    db.session.commit()

    flash('Dataset subido correctamente.', 'success')
    return redirect(url_for('datasets'))

if __name__ == '__main__':
    app.run(debug=True, threaded=True)
