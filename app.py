# app.py
import os
import io
import json
import traceback
from datetime import datetime
from uuid import uuid4

from flask import Flask, request, render_template, jsonify
import requests
from PIL import Image  # type: ignore

# Supabase client (import dynamically to avoid crash if lib não instalada)
try:
    from supabase import create_client, Client  # type: ignore
except Exception:
    create_client = None
    Client = None

# Optional: enable CORS if frontend is on different origin
try:
    from flask_cors import CORS  # type: ignore
except Exception:
    CORS = None

# -------------------------
# Config / secrets via env
# -------------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://agumdqjlbpbbohbxzoes.supabase.co")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", None)  # <<< set in env, do NOT commit
APPS_SCRIPT_URL = os.environ.get("APPS_SCRIPT_URL", "https://script.google.com/macros/s/AKfycby.../exec")
BASE_URL = os.environ.get("BASE_URL", "https://veiculosflex.onrender.com")

# local uploads fallback (optional)
LOCAL_UPLOAD_DIR = os.environ.get("LOCAL_UPLOAD_DIR", "uploads")

MAX_IMAGE_BYTES = int(os.environ.get("MAX_IMAGE_BYTES", 5 * 1024 * 1024))  # 5 MB default
ALLOWED_MIMES = {"image/jpeg", "image/png", "image/jpg", "image/webp"}

CAR_RECORDS_FILE = "car_records.json"

app = Flask(__name__)
if CORS:
    CORS(app)

# -------------------------
# Init Supabase safely
# -------------------------
supabase = None
if create_client and SUPABASE_ANON_KEY:
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
        print("Supabase client criado com sucesso.")
    except Exception as e:
        print("Erro ao criar Supabase client:", e)
        supabase = None
else:
    print("Supabase client não inicializado (create_client ou key ausente).")

# Ensure local upload dir exists (fallback/debug)
os.makedirs(LOCAL_UPLOAD_DIR, exist_ok=True)
os.makedirs(os.path.join(LOCAL_UPLOAD_DIR, "initial"), exist_ok=True)
os.makedirs(os.path.join(LOCAL_UPLOAD_DIR, "final"), exist_ok=True)


# -------------------------
# Helpers
# -------------------------
def load_car_records():
    if not os.path.exists(CAR_RECORDS_FILE):
        return []
    with open(CAR_RECORDS_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return []


def save_car_records(records):
    with open(CAR_RECORDS_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def safe_int(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        print(f"safe_int: não foi possível converter '{value}' para int")
        return None


def is_allowed_file(file_storage):
    if not file_storage:
        return False
    content_type = file_storage.content_type or ""
    if content_type.lower() not in ALLOWED_MIMES:
        return False
    # Try to check size:
    try:
        file_storage.stream.seek(0, io.SEEK_END)
        size = file_storage.stream.tell()
        file_storage.stream.seek(0)
        if size > MAX_IMAGE_BYTES:
            return False
    except Exception:
        # fallback: try read bytes length (but that consumes stream)
        try:
            raw = file_storage.read()
            file_storage.stream = io.BytesIO(raw)
            if len(raw) > MAX_IMAGE_BYTES:
                return False
        except Exception:
            return False
    return True


def generate_filename(cpf: str, key: str, ext: str = "jpg"):
    uid = uuid4().hex
    safe_cpf = (cpf or "unknown").replace("/", "_")
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    return f"{safe_cpf}_{key}_{ts}_{uid}.{ext}"


def save_locally(file_storage, subfolder: str, filename: str) -> str:
    path = os.path.join(LOCAL_UPLOAD_DIR, subfolder)
    os.makedirs(path, exist_ok=True)
    filepath = os.path.join(path, filename)
    file_storage.save(filepath)
    return filepath


def upload_image_to_supabase(file_storage, cpf, key):
    """
    Upload the image to Supabase storage and return a public URL.
    This function tries to be defensive across different supabase-py versions.
    Returns None on failure.
    """
    if not file_storage:
        return None

    if not is_allowed_file(file_storage):
        print("Upload blocked: file type/size not allowed:", getattr(file_storage, "content_type", None))
        return None

    # Read bytes once
    try:
        file_storage.stream.seek(0)
    except Exception:
        pass

    raw = file_storage.read()
    try:
        image = Image.open(io.BytesIO(raw))
        if image.mode != "RGB":
            image = image.convert("RGB")
        output = io.BytesIO()
        image.save(output, format="JPEG")
        file_bytes = output.getvalue()
        ext = "jpg"
    except Exception:
        # fallback: use raw bytes as-is
        file_bytes = raw
        ext = "jpg"

    filename = generate_filename(cpf, key, ext=ext)

    # Try Supabase upload
    if supabase:
        try:
            bucket = "photos"
            # Preferred pattern for current supabase-py: storage.from_(bucket).upload(...)
            try:
                storage = supabase.storage.from_(bucket)
                upload_result = storage.upload(filename, file_bytes, {"content-type": "image/jpeg"})
                # Many versions return dict-like or object. Try to get public URL:
                try:
                    pub = storage.get_public_url(filename)
                    # shape may vary
                    if isinstance(pub, dict):
                        public_url = pub.get("publicURL") or pub.get("public_url") or pub.get("publicUrl")
                    else:
                        public_url = pub
                except Exception as e:
                    print("warn: get_public_url failed:", e)
                    public_url = None

                # If public_url isn't a usable string, try constructing manually (best-effort)
                if not public_url:
                    public_url = f"{SUPABASE_URL}/storage/v1/object/public/{bucket}/{filename}"

                print(f"Upload supabase ok: {filename} -> {public_url}")
                return public_url
            except Exception as e_storage:
                # fallback: try top-level storage.upload if API different
                print("storage.from_ upload failed, tentando fallback:", e_storage)
                try:
                    upload_result = supabase.storage.upload(filename, file_bytes)
                    # try to fetch public url
                    pub = supabase.storage.get_public_url(filename)
                    public_url = pub.get("publicURL") if isinstance(pub, dict) else pub
                    if not public_url:
                        public_url = f"{SUPABASE_URL}/storage/v1/object/public/{bucket}/{filename}"
                    return public_url
                except Exception as e2:
                    print("erro no fallback de upload supabase:", e2)
                    traceback.print_exc()
        except Exception as e:
            print("Erro geral upload_image_to_supabase:", e)
            traceback.print_exc()

    # If Supabase not available or failed, save locally (useful for dev)
    try:
        local_name = filename
        local_path = os.path.join(LOCAL_UPLOAD_DIR, "fallback_" + local_name)
        with open(local_path, "wb") as f:
            f.write(file_bytes)
        # return a local path (note: not a public URL)
        print("Arquivo salvo localmente em:", local_path)
        return f"file://{os.path.abspath(local_path)}"
    except Exception as e:
        print("Erro salvando localmente:", e)
        traceback.print_exc()
        return None


# -------------------------
# Routes
# -------------------------
@app.route("/")
def index():
    return render_template("login.html")


@app.route("/login")
def login():
    return render_template("login.html")


@app.route("/submit_login", methods=["POST"])
def submit_login():
    """
    Accepts either JSON (fetch with JSON) or form data.
    Returns redirect URL for frontend.
    """
    data_json = None
    try:
        data_json = request.get_json(silent=True)
    except Exception:
        data_json = None

    if data_json:
        cpf = data_json.get("cpf")
        driver_name = data_json.get("driver_name")
    else:
        cpf = request.form.get("cpf")
        driver_name = request.form.get("driver_name")

    # small local fallback check
    records = load_car_records()
    existing = next((r for r in records if r.get("cpf") == cpf and r.get("status") == "initial"), None)

    # also try supabase quickly (defensive)
    if supabase and not existing:
        try:
            result = supabase.table("registro_kure").select("*").eq("cpf", cpf).eq("status", "initial").execute()
            if getattr(result, "error", None):
                print("submit_login: supabase error:", getattr(result, "error", None))
            else:
                if getattr(result, "data", None):
                    existing = result.data[0]
        except Exception as e:
            print("submit_login: supabase query failed:", e)

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
            if getattr(result, "error", None):
                print("form: supabase error:", getattr(result, "error", None))
            else:
                if getattr(result, "data", None):
                    existing = result.data[0]
        except Exception as e:
            print("form: supabase query failed:", e)

    if existing:
        return render_template("final_form.html", record=existing, cpf=cpf)
    else:
        return render_template("initial_form.html", cpf=cpf, driver_name=driver_name)


# -------------------------
# Submit initial
# -------------------------
@app.route("/submit_initial", methods=["POST"])
def submit_initial():
    try:
        form = request.form
        cpf = form.get("cpf")
        print("submit_initial - cpf:", cpf)

        # required fields
        required = ["requester_name", "driver_name", "initial_km", "origin", "initial_tank_level", "destination"]
        missing = [f for f in required if not form.get(f)]
        if missing:
            msg = f"Campos obrigatórios faltando: {', '.join(missing)}"
            print(msg)
            return jsonify({"status": "error", "message": msg}), 400

        # Validate & upload photos
        panel_file = request.files.get("initial_panel_photo")
        car_file = request.files.get("initial_car_photo")

        if not panel_file or not car_file:
            return jsonify({"status": "error", "message": "As duas fotos são obrigatórias."}), 400

        panel_url = upload_image_to_supabase(panel_file, cpf or "unknown", "initial_panel_photo")
        car_url = upload_image_to_supabase(car_file, cpf or "unknown", "initial_car_photo")

        now = datetime.utcnow()
        payload = {
            "cpf": cpf,
            "requester_name": form.get("requester_name"),
            "driver_name": form.get("driver_name"),
            "date": now.date().isoformat(),
            "initial_km": safe_int(form.get("initial_km")),
            "departure_time": now.isoformat(),
            "origin": form.get("origin"),
            "initial_tank_level": safe_int(form.get("initial_tank_level")),
            "destination": form.get("destination"),
            "car_status": form.get("car_status"),
            "reason": form.get("reason"),
            "vehicle_dirty": form.get("vehicle_dirty"),
            "vehicle_broken": form.get("vehicle_broken"),
            "vehicle_damaged": form.get("vehicle_damaged"),
            "observations": form.get("observations"),
            "initial_km_photo": panel_url,
            "car_status_photo": car_url,
            "status": "initial",
        }

        # Insert into Supabase (defensive)
        if supabase:
            try:
                result = supabase.table("registro_kure").insert(payload).execute()
                if getattr(result, "error", None):
                    print("submit_initial: supabase insert error:", getattr(result, "error", None))
                    # but continue to send Apps Script for traceability
                else:
                    print("submit_initial: supabase insert OK")
            except Exception as e:
                print("submit_initial: supabase insert threw:", e)
                traceback.print_exc()

        # Send to Apps Script (best-effort)
        try:
            resp = requests.post(APPS_SCRIPT_URL, json={"type": "initial", "data": payload}, timeout=10)
            print("Apps Script response (initial):", resp.status_code, resp.text)
        except Exception as e:
            print("Erro ao chamar Apps Script (initial):", e)
            traceback.print_exc()

        return jsonify({"status": "ok"})

    except Exception as e:
        print("Erro geral submit_initial:", e)
        traceback.print_exc()
        return jsonify({"status": "error", "message": "server error"}), 500


# -------------------------
# Submit final
# -------------------------
@app.route("/submit_final", methods=["POST"])
def submit_final():
    try:
        form = request.form
        cpf = form.get("cpf")
        print("submit_final - cpf:", cpf)

        required = ["final_km", "final_tank_level"]
        missing = [f for f in required if not form.get(f)]
        if missing:
            msg = f"Campos obrigatórios faltando: {', '.join(missing)}"
            print(msg)
            return jsonify({"status": "error", "message": msg}), 400

        # Find initial record (to merge data and build full payload)
        initial_record = None
        if supabase:
            try:
                res = supabase.table("registro_kure").select("*").eq("cpf", cpf).eq("status", "initial").execute()
                if getattr(res, "error", None):
                    print("submit_final: supabase select error:", getattr(res, "error", None))
                else:
                    if getattr(res, "data", None):
                        initial_record = res.data[0]
            except Exception as e:
                print("submit_final: supabase select threw:", e)
                traceback.print_exc()

        # Validate photos
        final_km_file = request.files.get("final_km_photo")
        final_tank_file = request.files.get("final_tank_photo")
        if not final_km_file or not final_tank_file:
            return jsonify({"status": "error", "message": "As duas fotos finais são obrigatórias."}), 400

        km_url = upload_image_to_supabase(final_km_file, cpf or "unknown", "final_km_photo")
        tank_url = upload_image_to_supabase(final_tank_file, cpf or "unknown", "final_tank_photo")

        now = datetime.utcnow()
        update_payload = {
            "final_km": safe_int(form.get("final_km")),
            "arrival_time": now.isoformat(),
            "final_tank_level": safe_int(form.get("final_tank_level")),
            "observations": form.get("observations"),
            "final_km_photo": km_url,
            "final_tank_photo": tank_url,
            "status": "complete",
        }

        # Update supabase row (defensive)
        if supabase:
            try:
                res_upd = supabase.table("registro_kure").update(update_payload).eq("cpf", cpf).eq("status", "initial").execute()
                if getattr(res_upd, "error", None):
                    print("submit_final: supabase update error:", getattr(res_upd, "error", None))
                else:
                    print("submit_final: supabase update OK")
            except Exception as e:
                print("submit_final: supabase update threw:", e)
                traceback.print_exc()

        # Build combined record for Apps Script:
        combined = {}
        if initial_record and isinstance(initial_record, dict):
            combined.update(initial_record)
        # override/add final fields:
        combined.update({
            "final_km": form.get("final_km"),
            "arrival_time": now.isoformat(),
            "final_tank_level": form.get("final_tank_level"),
            "observations": form.get("observations"),
            "final_km_photo": km_url,
            "final_tank_photo": tank_url,
            "status": "complete",
        })

        # Send to Apps Script
        try:
            resp = requests.post(APPS_SCRIPT_URL, json={"type": "final", "data": combined}, timeout=10)
            print("Apps Script response (final):", resp.status_code, resp.text)
        except Exception as e:
            print("Erro ao chamar Apps Script (final):", e)
            traceback.print_exc()

        return jsonify({"status": "ok"})

    except Exception as e:
        print("Erro geral submit_final:", e)
        traceback.print_exc()
        return jsonify({"status": "error", "message": "server error"}), 500


# -------------------------
# View records
# -------------------------
@app.route("/view_records")
def view_records():
    records = []
    if supabase:
        try:
            res = supabase.table("registro_kure").select("*").eq("status", "complete").execute()
            if getattr(res, "error", None):
                print("view_records: supabase error:", getattr(res, "error", None))
            else:
                records = res.data or []
        except Exception as e:
            print("view_records: supabase query threw:", e)
            traceback.print_exc()

    return render_template("registro.html", records=records)


# -------------------------
# Run
# -------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    host = "0.0.0.0" if os.environ.get("ENV", "development") != "local" else "127.0.0.1"
    app.run(host=host, port=port, debug=(os.environ.get("FLASK_DEBUG") == "1"))

