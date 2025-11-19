from flask import Flask, request, render_template, jsonify, send_file
import json
import os
from datetime import datetime
from io import BytesIO
import openpyxl
from openpyxl.styles import Font, Alignment, Border, Side
from supabase import create_client, Client
import requests
from PIL import Image
import io

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

APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbzOA_BkwPcKwTJQooGWISHUnPu6st1gSpf-Ov7RBA2_CrPxb2PRyhA_jckdZTmeYzd9Kw/exec"
BASE_URL = "https://veiculosflex.onrender.com"


def load_car_records():
    if not os.path.exists(CAR_RECORDS_FILE):
        return []
    with open(CAR_RECORDS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_car_records(records):
    with open(CAR_RECORDS_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


# ============================================================
# 🔥 Função para processar imagens e upar no Supabase
# ============================================================
def upload_image_to_supabase(file, cpf, key):
    try:
        filename = f"{cpf}_{key}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        raw = file.read()

        # Garantir imagem válida
        image = Image.open(io.BytesIO(raw))
        if image.mode != "RGB":
            image = image.convert("RGB")

        output = io.BytesIO()
        image.save(output, format="JPEG")
        file_content = output.getvalue()

        bucket = "photos"
        supabase.storage.from_(bucket).upload(filename, file_content, {"content-type": "image/jpeg"})
        return supabase.storage.from_(bucket).get_public_url(filename)

    except Exception as e:
        print(f"Erro ao processar ou enviar imagem {key}: {e}")
        return None


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
    records = load_car_records()
    existing = next((r for r in records if r.get("cpf") == cpf and r.get("status") == "initial"), None)

    if existing:
        return render_template("final_form.html", record=existing, cpf=cpf)
    else:
        return render_template("initial_form.html", cpf=cpf, driver_name=driver_name)


# ============================================================
# 🚗 SALVAR REGISTRO INICIAL
# ============================================================
@app.route("/submit_initial", methods=["POST"])
def submit_initial():
    try:
        data = request.form.to_dict()
        cpf = data.get("cpf")

        # ---------- 📅 PARSE DATE AND TIME ----------
        try:
            # Formato A: 31/10/2025 14:22:00
            dt = datetime.strptime(data.get("date_time"), "%d/%m/%Y %H:%M:%S")
            parsed_date = dt.date().isoformat()  # YYYY-MM-DD
            parsed_departure_time = dt.time().isoformat()  # HH:MM:SS
        except Exception as e:
            print(f"Erro ao converter data/hora: {e}")
            return jsonify({"status": "error", "message": "Formato de data inválido"}), 400

        # ---------- 📸 PROCESSAR FOTOS ----------
        photos = {}
        for key in request.files:
            file = request.files[key]
            if file.filename:
                photos[key] = upload_image_to_supabase(file, cpf, key)

        # ---------- Criar registro local ----------
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
            "initial_km_photo": photos.get("initial_km_photo"),
            "initial_tank_photo": photos.get("initial_tank_photo"),
            "car_status_photo": photos.get("car_status_photo"),
            "status": "initial",
        }

        # ---------- 💾 SALVAR NO SUPABASE ----------
        if supabase:
            try:
                payload = {
                    "cpf": record["cpf"],
                    "requester_name": record["requester_name"],
                    "driver_name": record["driver_name"],
                    "date": record["date"],
                    "initial_km": int(record["initial_km"]),
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
                    "initial_km_photo": record["initial_km_photo"],
                    "initial_tank_photo": record["initial_tank_photo"],
                    "car_status_photo": record["car_status_photo"],
                    "status": "initial",
                }

                result = supabase.table("registro_kure").insert(payload).execute()
                print("RESULTADO DO SUPABASE INSERT:", result)

            except Exception as e:
                print(f"Erro Supabase INSERT: {e}")

        # ---------- Salvar local ----------
        records = load_car_records()
        records.append(record)
        save_car_records(records)

        # ---------- Enviar email ----------
        try:
            requests.post(APPS_SCRIPT_URL, json={"type": "initial", "data": record})
        except:
            pass

        return jsonify({"status": "ok"})

    except Exception as e:
        print("Erro geral:", e)
        return jsonify({"status": "error"}), 500


# ============================================================
# 🚗 SALVAR REGISTRO FINAL
# ============================================================
@app.route("/submit_final", methods=["POST"])
def submit_final():
    try:
        data = request.form.to_dict()
        cpf = data.get("cpf")

        # ---------- 📸 Fotos finais ----------
        photos = {}
        for key in request.files:
            file = request.files[key]
            if file.filename:
                photos[key] = upload_image_to_supabase(file, cpf, key)

        # ---------- Hora de chegada ----------
        arrival_time_str = data.get("arrival_time")
        try:
            dt = datetime.strptime(arrival_time_str, "%d/%m/%Y %H:%M:%S")
            arrival_time = dt.time().isoformat()
        except:
            arrival_time = None

        # ---------- Atualizar Supabase ----------
        if supabase:
            try:
                update_payload = {
                    "final_km": int(data.get("final_km")),
                    "arrival_time": arrival_time,
                    "final_tank_level": data.get("final_tank_level"),
                    "observations": data.get("observations"),
                    "final_km_photo": photos.get("final_km_photo"),
                    "final_tank_photo": photos.get("final_tank_photo"),
                    "status": "complete",
                }

                result = (
                    supabase.table("registro_kure")
                    .update(update_payload)
                    .eq("cpf", cpf)
                    .eq("status", "initial")
                    .execute()
                )

                print("RESULTADO UPDATE:", result)

            except Exception as e:
                print(f"Erro Supabase UPDATE: {e}")

        # ---------- Atualizar JSON local ----------
        records = load_car_records()
        for r in records:
            if r["cpf"] == cpf and r["status"] == "initial":
                r.update(update_payload)
                r["status"] = "complete"
                break

        save_car_records(records)

        # ---------- Email ----------
        try:
            requests.post(APPS_SCRIPT_URL, json={"type": "final", "data": r})
        except:
            pass

        return jsonify({"status": "ok"})

    except Exception as e:
        print("Erro geral final:", e)
        return jsonify({"status": "error"}), 500


# ============================================================
# RESTO DO CÓDIGO (EXCEL, ADMIN, ETC) — permanece igual
# ============================================================
@app.route("/view_records")
def view_records():
    records = load_car_records()
    complete = [r for r in records if r.get("status") == "complete"]
    return render_template("registro.html", records=complete)


# ... (restante do código permanece igual ao anterior) ...


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
