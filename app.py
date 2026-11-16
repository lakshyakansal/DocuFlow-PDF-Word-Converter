import os, uuid, subprocess, shutil
from datetime import datetime
from functools import wraps
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, abort
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from pdf2docx import Converter

BASE = Path(__file__).resolve().parent
UPLOAD_DIR = BASE / 'storage' / 'uploads'
OUTPUT_DIR = BASE / 'storage' / 'outputs'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True); OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
app = Flask(__name__)
app.config.update(SECRET_KEY=os.getenv('SECRET_KEY', 'change-this-secret-before-deploying'), SQLALCHEMY_DATABASE_URI=os.getenv('DATABASE_URL', 'sqlite:///' + str(BASE/'docuflow.db')).replace('postgres://','postgresql://'), SQLALCHEMY_TRACK_MODIFICATIONS=False, MAX_CONTENT_LENGTH=25*1024*1024)
db = SQLAlchemy(app)

class User(db.Model):
    id=db.Column(db.Integer, primary_key=True); username=db.Column(db.String(80), unique=True, nullable=False); password_hash=db.Column(db.String(255), nullable=False); role=db.Column(db.String(20), default='user'); created_at=db.Column(db.DateTime, default=datetime.utcnow)
class Conversion(db.Model):
    id=db.Column(db.Integer, primary_key=True); user_id=db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False); original_name=db.Column(db.String(255)); output_name=db.Column(db.String(255)); conversion_type=db.Column(db.String(30)); status=db.Column(db.String(20), default='completed'); created_at=db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()
    admin_name=os.getenv('ADMIN_USERNAME','admin'); admin_pass=os.getenv('ADMIN_PASSWORD','ChangeMe123!')
    if not User.query.filter_by(username=admin_name).first():
        db.session.add(User(username=admin_name,password_hash=generate_password_hash(admin_pass),role='admin')); db.session.commit()

def login_required(fn):
    @wraps(fn)
    def wrapped(*a,**kw):
        if 'user_id' not in session: return redirect(url_for('login', next=request.path))
        return fn(*a,**kw)
    return wrapped
def admin_required(fn):
    @wraps(fn)
    def wrapped(*a,**kw):
        if 'user_id' not in session: return redirect(url_for('login'))
        u=db.session.get(User,session['user_id'])
        if not u or u.role!='admin': abort(403)
        return fn(*a,**kw)
    return wrapped

@app.context_processor
def inject_user(): return {'current_user': db.session.get(User,session.get('user_id')) if session.get('user_id') else None}
@app.route('/')
def home(): return render_template('index.html')
@app.route('/register',methods=['GET','POST'])
def register():
    if request.method=='POST':
        username=request.form.get('username','').strip(); password=request.form.get('password','')
        if len(username)<3 or len(password)<8: flash('Use a username of 3+ characters and password of at least 8 characters.','error')
        elif User.query.filter_by(username=username).first(): flash('That username is already taken.','error')
        else:
            u=User(username=username,password_hash=generate_password_hash(password)); db.session.add(u); db.session.commit(); session['user_id']=u.id; flash('Your account is ready.','success'); return redirect(url_for('dashboard'))
    return render_template('auth.html', mode='register')
@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        u=User.query.filter_by(username=request.form.get('username','').strip()).first()
        if u and check_password_hash(u.password_hash,request.form.get('password','')):
            session.clear(); session['user_id']=u.id; return redirect(url_for('admin') if u.role=='admin' else url_for('dashboard'))
        flash('Incorrect username or password.','error')
    return render_template('auth.html',mode='login')
@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('home'))
@app.route('/dashboard')
@login_required
def dashboard():
    jobs=Conversion.query.filter_by(user_id=session['user_id']).order_by(Conversion.created_at.desc()).limit(30).all()
    return render_template('dashboard.html',jobs=jobs)
@app.route('/convert',methods=['POST'])
@login_required
def convert():
    f=request.files.get('file'); kind=request.form.get('kind')
    if not f or not f.filename: flash('Choose a file first.','error'); return redirect(url_for('dashboard'))
    allowed={'pdf-to-word':'.pdf','word-to-pdf':'.docx'}
    if kind not in allowed or Path(f.filename).suffix.lower()!=allowed[kind]: flash('Please upload a supported '+('PDF' if kind=='pdf-to-word' else 'DOCX')+' file.','error'); return redirect(url_for('dashboard'))
    token=uuid.uuid4().hex; safe=secure_filename(f.filename) or ('document'+allowed[kind]); source=UPLOAD_DIR/(token+allowed[kind]); f.save(source)
    out_ext='.docx' if kind=='pdf-to-word' else '.pdf'; output=OUTPUT_DIR/(token+out_ext)
    try:
        if kind=='pdf-to-word':
            cv=Converter(str(source)); cv.convert(str(output)); cv.close()
        else:
            soffice=shutil.which('libreoffice') or shutil.which('soffice')
            if not soffice: raise RuntimeError('PDF export engine is missing. Install LibreOffice or use the provided Dockerfile.')
            profile=BASE/'storage'/('lo-'+token); profile.mkdir(parents=True,exist_ok=True)
            p=subprocess.run([soffice,'-env:UserInstallation='+profile.as_uri(),'--headless','--convert-to','pdf','--outdir',str(OUTPUT_DIR),str(source)],capture_output=True,text=True,timeout=90)
            generated=OUTPUT_DIR/(source.stem+'.pdf')
            if p.returncode!=0 or not generated.exists(): raise RuntimeError((p.stderr or p.stdout or 'LibreOffice conversion failed')[-500:])
            generated.replace(output); shutil.rmtree(profile,ignore_errors=True)
        if not output.exists() or output.stat().st_size==0: raise RuntimeError('The converter did not produce an output file.')
        job=Conversion(user_id=session['user_id'],original_name=safe,output_name=output.name,conversion_type=kind); db.session.add(job); db.session.commit(); flash('Conversion complete. Your file is ready to download.','success'); return redirect(url_for('dashboard'))
    except Exception as e:
        output.unlink(missing_ok=True); flash('Conversion failed: '+str(e),'error'); return redirect(url_for('dashboard'))
    finally: source.unlink(missing_ok=True)
@app.route('/download/<int:job_id>')
@login_required
def download(job_id):
    job=db.session.get(Conversion,job_id)
    if not job or (job.user_id!=session['user_id'] and (not current_user or current_user.role!='admin')): abort(404)
    path=OUTPUT_DIR/job.output_name
    if not path.exists(): abort(404)
    return send_from_directory(OUTPUT_DIR,job.output_name,as_attachment=True,download_name=Path(job.original_name).stem+('.docx' if job.conversion_type=='pdf-to-word' else '.pdf'))
@app.route('/admin')
@admin_required
def admin(): return render_template('admin.html',users=User.query.order_by(User.created_at.desc()).all(),jobs=Conversion.query.order_by(Conversion.created_at.desc()).limit(100).all(),total_users=User.query.count(),total_jobs=Conversion.query.count())
@app.errorhandler(413)
def too_large(e): flash('File is too large. Maximum upload size is 25 MB.','error'); return redirect(url_for('dashboard'))
if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.getenv('PORT',5000)),debug=os.getenv('FLASK_DEBUG')=='1')
