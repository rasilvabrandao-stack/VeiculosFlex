from flask import Flask, request, render_template, jsonify, send_file
import json
import os
from datetime import datetime
from io import BytesIO
import openpyxl
from openpyxl.styles import Font, Alignment, Border, Side
from supabase import create_client, Client
import requests

app = Flask(__name__)

CAR_RECORDS_FILE = "car_records.json"

# Supabase configuration
SUPABASE_URL = "https://agumdqjlbpbbohbxzoes.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFndW1kcWpsYnBiYm9oYnh6b2VzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjIzNTU5NTEsImV4cCI6MjA3NzkzMTk1MX0.DX_W3XL4zj9gs-XC0O3aUptYdhjF9sda2qkj_E-aKx0"
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
except Exception as e:
    print(f"Erro ao conectar ao Supabase: {e}")
    supabase = None

# Google Apps Script URL for email notifications
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbyO7efjJ_WX9En8MqfFfNeTxpThEs2gFSfUgSshAoNeZqseIvOBOf2KxtbmK1MXIJ5aCA/exec"

def load_car_records():
    if not os.path.exists(CAR_RECORDS_FILE):
        return []
    with open(CAR_RECORDS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_car_records(records):
    with open(CAR_RECORDS_FILE, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/submit_login', methods=['POST'])
def submit_login():
    data = request.get_json()
    cpf = data.get('cpf')
    driver_name = data.get('driver_name')
    records = load_car_records()
    existing_record = next((r for r in records if r.get('cpf') == cpf and r.get('status') == 'initial'), None)
    if existing_record:
        return jsonify({"redirect": f"/form/{cpf}"})
    else:
        return jsonify({"redirect": f"/form/{cpf}?name={driver_name}"})

@app.route('/form/<cpf>')
def form(cpf):
    driver_name = request.args.get('name')
    records = load_car_records()
    existing_record = next((r for r in records if r.get('cpf') == cpf and r.get('status') == 'initial'), None)
    if existing_record:
        return render_template('final_form.html', record=existing_record, cpf=cpf)
    else:
        return render_template('initial_form.html', cpf=cpf, driver_name=driver_name)

@app.route('/submit_initial', methods=['POST'])
def submit_initial():
    try:
        data = request.form.to_dict()
        cpf = data.get('cpf')
        photos = {}
        for key in request.files:
            file = request.files[key]
            if file and file.filename:
                filename = f"{cpf}_{key}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                filepath = os.path.join('static', 'photos', filename)
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                file.save(filepath)
                photos[key] = filepath

        record = {
            'cpf': cpf,
            'requester_name': data.get('requester_name'),
            'driver_name': data.get('driver_name'),
            'date': data.get('date_time'),  # Changed from 'date' to 'date_time' to match form
            'initial_km': data.get('initial_km'),
            'departure_time': data.get('departure_time'),
            'origin': data.get('origin'),
            'initial_tank_level': data.get('initial_tank_level'),
            'destination': data.get('destination'),
            'car_status': data.get('car_status'),
            'initial_km_photo': photos.get('initial_km_photo'),
            'initial_tank_photo': photos.get('initial_tank_photo'),
            'car_status_photo': photos.get('car_status_photo'),
            'status': 'initial'
        }
        # Insert into Supabase
        if supabase:
            try:
                supabase.table('registros').insert({
                    'cpf': record['cpf'],
                    'requester_name': record['requester_name'],
                    'driver_name': record['driver_name'],
                    'date': record['date'],
                    'initial_km': record['initial_km'],
                    'departure_time': record['departure_time'],
                    'origin': record['origin'],
                    'initial_tank_level': record['initial_tank_level'],
                    'destination': record['destination'],
                    'car_status': record['car_status'],
                    'initial_km_photo': record['initial_km_photo'],
                    'initial_tank_photo': record['initial_tank_photo'],
                    'car_status_photo': record['car_status_photo'],
                    'status': 'initial'
                }).execute()
            except Exception as e:
                print(f"Erro ao salvar no Supabase: {str(e)}")
                # Continue without Supabase if it fails

        records = load_car_records()
        records.append(record)
        save_car_records(records)

        # Send email notification for initial save
        try:
            payload = {
                "type": "initial",
                "data": record
            }
            response = requests.post(APPS_SCRIPT_URL, json=payload, timeout=10)
            print(f"Email response status: {response.status_code}")
        except Exception as e:
            print(f"Erro ao enviar email para save inicial: {e}")

        return jsonify({"status": "ok"})
    except Exception as e:
        print(f"Erro geral no submit_initial: {str(e)}")
        return jsonify({"status": "error", "message": f"Erro interno: {str(e)}"}), 500

@app.route('/submit_final', methods=['POST'])
def submit_final():
    try:
        data = request.form.to_dict()
        cpf = data.get('cpf')
        photos = {}
        for key in request.files:
            file = request.files[key]
            if file and file.filename:
                filename = f"{cpf}_{key}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                filepath = os.path.join('static', 'photos', filename)
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                file.save(filepath)
                photos[key] = filepath

        # Update in Supabase
        if supabase:
            try:
                supabase.table('registros').update({
                    'final_km': data.get('final_km'),
                    'arrival_time': data.get('arrival_time'),
                    'final_tank_level': data.get('final_tank_level'),
                    'final_km_photo': photos.get('final_km_photo'),
                    'final_tank_photo': photos.get('final_tank_photo'),
                    'status': 'complete'
                }).eq('cpf', cpf).eq('status', 'initial').execute()
            except Exception as e:
                print(f"Erro ao atualizar no Supabase: {str(e)}")
                # Continue without Supabase if it fails

        records = load_car_records()
        for record in records:
            if record.get('cpf') == cpf and record.get('status') == 'initial':
                record.update({
                    'final_km': data.get('final_km'),
                    'arrival_time': data.get('arrival_time'),
                    'final_tank_level': data.get('final_tank_level'),
                    'final_km_photo': photos.get('final_km_photo'),
                    'final_tank_photo': photos.get('final_tank_photo'),
                    'status': 'complete'
                })
                # Send email notification for final save
                try:
                    payload = {
                        "type": "final",
                        "data": record
                    }
                    response = requests.post(APPS_SCRIPT_URL, json=payload, timeout=10)
                    print(f"Email response status: {response.status_code}")
                except Exception as e:
                    print(f"Erro ao enviar email para save final: {e}")
                break
        save_car_records(records)
        return jsonify({"status": "ok"})
    except Exception as e:
        print(f"Erro geral no submit_final: {str(e)}")
        return jsonify({"status": "error", "message": f"Erro interno: {str(e)}"}), 500

@app.route('/view_records')
def view_records():
    records = load_car_records()
    complete_records = [r for r in records if r.get('status') == 'complete']
    return render_template('registro.html', records=complete_records)

@app.route('/admin_login')
def admin_login():
    return render_template('admin_login.html')

@app.route('/submit_admin_login', methods=['POST'])
def submit_admin_login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    # Simple authentication - in production, use proper hashing and database
    if username == 'admin' and password == 'admin123':
        return jsonify({"redirect": "/admin_dashboard"})
    else:
        return jsonify({"error": "Credenciais inválidas"}), 401

@app.route('/admin_dashboard')
def admin_dashboard():
    if supabase:
        try:
            # Fetch all records from Supabase
            response = supabase.table('registros').select('*').execute()
            all_records = response.data
        except Exception as e:
            # Fallback to local JSON if Supabase fails
            records = load_car_records()
            all_records = [r for r in records if r.get('status') in ['initial', 'complete']]
    else:
        # Fallback to local JSON if Supabase is not available
        records = load_car_records()
        all_records = [r for r in records if r.get('status') in ['initial', 'complete']]
    return render_template('admin_dashboard.html', records=all_records)

@app.route('/download_excel')
def download_excel():
    if supabase:
        try:
            # Fetch data from Supabase
            response = supabase.table('registros').select('*').execute()
            registros = response.data
            complete_records = [r for r in registros if r.get('status') == 'complete']
        except Exception as e:
            return jsonify({"status": "error", "message": f"Erro ao buscar dados do Supabase: {str(e)}"})
    else:
        # Fallback to local JSON if Supabase is not available
        records = load_car_records()
        complete_records = [r for r in records if r.get('status') == 'complete']

    # Create Excel workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Registros de Carro"

    # Define styles
    header_font = Font(bold=True)
    header_alignment = Alignment(horizontal='center')
    thin_border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))

    # Headers
    headers = ['CPF', 'Nome do Solicitante', 'Nome do Motorista', 'Data', 'Km Inicial', 'Horário de Saída', 'Origem', 'Nível Inicial do Tanque', 'Destino', 'Km Final', 'Hora de Chegada', 'Nível Final do Tanque']
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.font = header_font
        cell.alignment = header_alignment
        cell.border = thin_border

    # Data
    for row_num, record in enumerate(complete_records, 2):
        ws.cell(row=row_num, column=1, value=record.get('cpf')).border = thin_border
        ws.cell(row=row_num, column=2, value=record.get('requester_name')).border = thin_border
        ws.cell(row=row_num, column=3, value=record.get('driver_name')).border = thin_border
        ws.cell(row=row_num, column=4, value=record.get('date')).border = thin_border
        ws.cell(row=row_num, column=5, value=record.get('initial_km')).border = thin_border
        ws.cell(row=row_num, column=6, value=record.get('departure_time')).border = thin_border
        ws.cell(row=row_num, column=7, value=record.get('origin')).border = thin_border
        ws.cell(row=row_num, column=8, value=record.get('initial_tank_level')).border = thin_border
        ws.cell(row=row_num, column=9, value=record.get('destination')).border = thin_border
        ws.cell(row=row_num, column=10, value=record.get('final_km')).border = thin_border
        ws.cell(row=row_num, column=11, value=record.get('arrival_time')).border = thin_border
        ws.cell(row=row_num, column=12, value=record.get('final_tank_level')).border = thin_border

    # Adjust column widths
    column_widths = [15, 20, 20, 12, 12, 15, 15, 20, 15, 12, 15, 20]
    for col_num, width in enumerate(column_widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(col_num)].width = width

    # Save to BytesIO
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(output, download_name='registros_carro.xlsx', as_attachment=True)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
