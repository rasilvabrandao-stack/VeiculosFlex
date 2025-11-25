app.py
from flask import Flask, request, render_template, jsonify, send_file
import json
import os
from datetime import datetime
from io import BytesIO
from supabase import create_client, Client
import requests
from PIL import Image  # pyright: ignore[reportMissingImports]
import io
import traceback

app = Flask(__name__)

# === Configurações ===
CAR_RECORDS_FILE = "car_records.json"

SUPABASE_URL = "https://agumdqjlbpbbohbxzoes.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFndW1kcWpsYnBiYm9oYnh6b2VzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjIzNTU5NTEsImV4cCI6MjA3NzkzMTk1MX0.DX_W3XL4zj9gs-XC0O3aUptYdhjF9sda2qkj_E-aKx0"

APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbyh5QgBJuwC9A1nfzu_Utk8axSJsW9Eaqa0NzNeLXJMMc0poz5UQg48SolUAhrXkW5zkQ/exec"
BASE_URL = "https://veiculosflex.onrender.com"

# === Inicializar Supabase ===
supabase = None
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    print("Supabase client criado com sucesso.")
except Exception as e:
    print("Erro ao conectar ao Supabase:", e)
    supabase = None

# ====================
# Helpers
# ====================
def load_car_records():
    if not os.path.exists(CAR_RECORDS_FILE):
        return []
    with open(CAR_RECORDS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_car_records(records):
    with open(CAR_RECORDS_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

def safe_int(value):
    try:
        return int(value) if value not in (None, "") else None
    except Exception:
        return None

# ============================================================
# Upload de imagem para Supabase (retorna URL pública ou None)
# ============================================================
def upload_image_to_supabase(file, cpf, key):
    if not supabase:
        print("Supabase não inicializado — skipping upload_image_to_supabase")
        return None
    try:
        filename = f"{cpf or 'unknown'}_{key}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        raw = file.read()
        image = Image.open(io.BytesIO(raw))
        if image.mode != "RGB":
            image = image.convert("RGB")
        output = io.BytesIO()
        image.save(output, format="JPEG")
        file_content = output.getvalue()

        bucket = "photos"
        storage = supabase.storage.from_(bucket)

        upload_result = storage.upload(filename, file_content, {"content-type": "image/jpeg"})
        print(f"Upload result for {filename}:", upload_result)

        pub = storage.get_public_url(filename)
        print(f"Public URL raw for {filename}:", pub)
        public_url = None
        if isinstance(pub, dict):
            public_url = pub.get("publicURL") or pub.get("public_url") or pub.get("publicUrl")
        elif isinstance(pub, str):
            public_url = pub
        else:
            public_url = str(pub)

        print(f"Image uploaded: {filename}, url: {public_url}")
        return public_url

    except Exception as e:
        print(f"Erro ao processar ou enviar imagem {key}: {e}")
        traceback.print_exc()
        return None

# ====================
# Rotas
# ====================
@app.route("/")
def index():
    return render_template("login.html")

@app.route("/login")
def login():
    return render_template("login.html")

@app.route("/submit_login", methods=["POST"])
def submit_login():
    data = request.get_json()
    cpf = data.get("cpf")
    driver_name = data.get("driver_name")
    records = load_car_records()
    existing = next((r for r in records if r.get("cpf") == cpf and r.get("status") == "initial"), None)
    if existing:
        return jsonify({"redirect": f"/form/{cpf}"})
    else:
        return jsonify({"redirect": f"/form/{cpf}?name={driver_name}"})

@app.route("/form/<cpf>")
def form(cpf):
    driver_name = request.args.get("name")
    existing = None
    if supabase:
        try:
            result = supabase.table("registro_kure").select("*").eq("cpf", cpf).eq("status", "initial").execute()
            print("Consulta registro_kure:", getattr(result, "data", None), getattr(result, "error", None))
            existing = result.data[0] if result.data else None
        except Exception as e:
            print("Erro ao consultar Supabase:", e)
            traceback.print_exc()
            existing = None
    if existing:
        return render_template("final_form.html", record=existing, cpf=cpf)
    else:
        return render_template("initial_form.html", cpf=cpf, driver_name=driver_name)

# ============================================================
# SALVAR REGISTRO INICIAL (submit_initial)
# ============================================================
@app.route("/submit_initial", methods=["POST"])
def submit_initial():
    try:
        data = request.form.to_dict()
        print("submit_initial - form data:", data)

        # Validação: campos obrigatórios conforme schema
        required = ["requester_name", "driver_name", "initial_km", "origin", "initial_tank_level", "destination"]
        missing = [f for f in required if not data.get(f)]
        if missing:
            msg = f"Campos obrigatórios faltando: {', '.join(missing)}"
            print(msg)
            return jsonify({"status": "error", "message": msg}), 400

        cpf = data.get("cpf")
        now = datetime.now()
        parsed_date = now.date().isoformat()
        parsed_departure_time = now.time().isoformat()

        # Processar fotos do request.files (chaves vindas do formulário)
        photos = {}
        for key in request.files:
            file = request.files[key]
            if file and getattr(file, "filename", ""):
                photos[key] = upload_image_to_supabase(file, cpf or "unknown", key)

        # Monta record (para envio ao Apps Script)
        record = {
            "cpf": cpf,
            "requester_name": data.get("requester_name"),
            "driver_name": data.get("driver_name"),
            "date": parsed_date,
            "initial_km": data.get("initial_km"),
            "departure_time": parsed_departure_time,
            "origin": data.get("origin"),
            "initial_tank_level": data.get("initial_tank_level"),
            "destination": data.get("destination"),
            "car_status": data.get("car_status"),
            "reason": data.get("reason"),
            "vehicle_dirty": data.get("vehicle_dirty"),
            "vehicle_broken": data.get("vehicle_broken"),
            "vehicle_damaged": data.get("vehicle_damaged"),
            "observations": data.get("observations"),
            # mapping: form -> db
            "initial_km_photo": photos.get("initial_panel_photo"),
            "car_status_photo": photos.get("initial_car_photo"),
            "status": "initial",
        }

        # Prepara payload para inserir no Supabase (nomes devem casar com SQL)
        payload = {
            "cpf": record["cpf"],
            "requester_name": record["requester_name"],
            "driver_name": record["driver_name"],
            "date": record["date"],
            "initial_km": safe_int(record["initial_km"]),
            "departure_time": record["departure_time"],
            "origin": record["origin"],
            "initial_tank_level": record["initial_tank_level"],
            "destination": record["destination"],
            "car_status": record["car_status"],
            "reason": record["reason"],
            "vehicle_dirty": record["vehicle_dirty"],
            "vehicle_broken": record["vehicle_broken"],
            "vehicle_damaged": record["vehicle_damaged"],
            "observations": record["observations"],
            # gravar nas colunas corretas:
            "initial_km_photo": record["initial_km_photo"],
            "car_status_photo": record["car_status_photo"],
            "status": "initial",
        }

        # Inserir no Supabase
        if supabase:
            try:
                result = supabase.table("registro_kure").insert(payload).execute()
                print("=== SUPABASE INSERT RESPONSE ===")
                print("data:", getattr(result, "data", None))
                print("error:", getattr(result, "error", None))
                print("raw:", result)
                print("=== END SUPABASE INSERT ===")
                if getattr(result, "error", None):
                    return jsonify({"status": "error", "message": str(result.error)}), 500
            except Exception as e:
                print("Erro Supabase INSERT:", e)
                traceback.print_exc()
                return jsonify({"status": "error", "message": "supabase insert failed"}), 500
        else:
            print("Supabase não inicializado - registro não inserido.")

        # Enviar para Apps Script (email)
        try:
            resp = requests.post(APPS_SCRIPT_URL, json={"type": "initial", "data": record}, timeout=10)
            print("=== APPS SCRIPT RESPONSE (initial) ===")
            print("status:", resp.status_code)
            print("text:", resp.text)
            print("headers:", resp.headers)
            print("=== END APPS SCRIPT ===")
            # se quiser tratar erro do Apps Script como falha, descomente o bloco seguinte:
            # if resp.status_code >= 400:
            #     return jsonify({"status":"error","message":"apps script error"}), 500
        except Exception as e:
            print("Erro ao chamar Apps Script:", e)
            traceback.print_exc()

        return jsonify({"status": "ok"})

    except Exception as e:
        print("Erro geral submit_initial:", e)
        traceback.print_exc()
        return jsonify({"status": "error", "message": "server error"}), 500

# ============================================================
# SALVAR REGISTRO FINAL (submit_final)
# ============================================================
@app.route("/submit_final", methods=["POST"])
def submit_final():
    try:
        data = request.form.to_dict()
        print("submit_final - form data:", data)

        # Validação mínima
        required = ["final_km", "final_tank_level"]
        missing = [f for f in required if not data.get(f)]
        if missing:
            msg = f"Campos obrigatórios faltando: {', '.join(missing)}"
            print(msg)
            return jsonify({"status": "error", "message": msg}), 400

        cpf = data.get("cpf")
        photos = {}
        for key in request.files:
            file = request.files[key]
            if file and getattr(file, "filename", ""):
                photos[key] = upload_image_to_supabase(file, cpf or "unknown", key)

        now = datetime.now()
        arrival_time = now.time().isoformat()

        update_payload = {
            "final_km": safe_int(data.get("final_km")),
            "arrival_time": arrival_time,
            "final_tank_level": data.get("final_tank_level"),
            "observations": data.get("observations"),
            # map fotos finais diretamente (nomes batem com o schema)
            "final_km_photo": photos.get("final_km_photo"),
            "final_tank_photo": photos.get("final_tank_photo"),
            "status": "complete",
        }

        if supabase:
            try:
                result = (
                    supabase.table("registro_kure")
                    .update(update_payload)
                    .eq("cpf", cpf)
                    .eq("status", "initial")
                    .execute()
                )
                print("=== SUPABASE UPDATE RESPONSE ===")
                print("data:", getattr(result, "data", None))
                print("error:", getattr(result, "error", None))
                print("raw:", result)
                print("=== END SUPABASE UPDATE ===")
                if getattr(result, "error", None):
                    return jsonify({"status": "error", "message": str(result.error)}), 500
            except Exception as e:
                print("Erro Supabase UPDATE:", e)
                traceback.print_exc()
                return jsonify({"status": "error", "message": "supabase update failed"}), 500
        else:
            print("Supabase não inicializado - skipping update.")

        # Enviar ao Apps Script
        try:
            record = {
                "cpf": cpf,
                "final_km": data.get("final_km"),
                "arrival_time": arrival_time,
                "final_tank_level": data.get("final_tank_level"),
                "observations": data.get("observations"),
                "final_km_photo": photos.get("final_km_photo"),
                "final_tank_photo": photos.get("final_tank_photo"),
                "status": "complete",
            }
            resp = requests.post(APPS_SCRIPT_URL, json={"type": "final", "data": record}, timeout=10)
            print("=== APPS SCRIPT RESPONSE (final) ===")
            print("status:", resp.status_code)
            print("text:", resp.text)
            print("headers:", resp.headers)
            print("=== END APPS SCRIPT ===")
        except Exception as e:
            print("Erro ao chamar Apps Script (final):", e)
            traceback.print_exc()

        return jsonify({"status": "ok"})

    except Exception as e:
        print("Erro geral final:", e)
        traceback.print_exc()
        return jsonify({"status": "error", "message": "server error"}), 500

# ============================================================
# View records
# ============================================================
@app.route("/view_records")
def view_records():
    complete = []
    if supabase:
        try:
            result = supabase.table("registro_kure").select("*").eq("status", "complete").execute()
            print("view_records result:", getattr(result, "data", None), getattr(result, "error", None))
            complete = result.data or []
        except Exception as e:
            print("Erro ao consultar Supabase:", e)
            traceback.print_exc()
            complete = []
    return render_template("registro.html", records=complete)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
