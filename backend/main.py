from fastapi import FastAPI, Depends, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import database, uuid, datetime

app = FastAPI(title="Sync Server - Mini Crèche")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
templates = Jinja2Templates(directory="templates")

# ── Modèles ────────────────────────────────────────────────────────────────────

class EmargementSync(BaseModel):
    id: str; creche_name: str; employee_id: str; employee_name: str
    type_event: str; timestamp: str; signature: str

class LoginRequest(BaseModel):
    username: str; password: str

class ScheduleEntry(BaseModel):
    jour: int; matin_debut: str; matin_fin: str; aprem_debut: str; aprem_fin: str
    no_pointage: bool = False

class ScheduleExceptionEntry(BaseModel):
    date: str; label: str = "Journée exceptionnelle"
    matin_debut: str = ""; matin_fin: str = ""; aprem_debut: str = ""; aprem_fin: str = ""
    no_pointage: bool = False

class CrecheCreate(BaseModel):
    nom: str; password: str

class CrecheUpdate(BaseModel):
    password: str

class EmployeeCreate(BaseModel):
    nom: str; prenom: str; role: str = ""

class AssignmentCreate(BaseModel):
    employee_id: str; creche_nom: str

class TimeclockUpdate(BaseModel):
    enabled: bool
    creche: str

# ── Helpers ────────────────────────────────────────────────────────────────────

def calc(start: str, end: str) -> int:
    if not start or not end:
        return 0
    try:
        sh, sm = map(int, start.split(":")); eh, em = map(int, end.split(":"))
        return max(0, (eh*60+em)-(sh*60+sm))
    except:
        return 0

def timeclock_enabled(db: Session, creche: str = "") -> bool:
    """Each crèche has its own switch; old global records remain a fallback."""
    query = db.query(database.TimeclockState)
    if creche:
        query = query.filter(database.TimeclockState.creche_nom == creche)
    state = query.order_by(database.TimeclockState.id.desc()).first()
    if not state and creche:
        state = db.query(database.TimeclockState).filter(database.TimeclockState.creche_nom.is_(None)).order_by(database.TimeclockState.id.desc()).first()
    return bool(state and state.enabled)

def timeclock_enabled_on(db: Session, day: datetime.date, creche: str = "") -> bool:
    """The state is effective from its change date, with the initial state off."""
    enabled = False
    q = db.query(database.TimeclockState)
    if creche:
        q = q.filter(database.TimeclockState.creche_nom == creche)
    states = q.order_by(database.TimeclockState.id.asc()).all()
    if not states and creche:
        states = db.query(database.TimeclockState).filter(database.TimeclockState.creche_nom.is_(None)).order_by(database.TimeclockState.id.asc()).all()
    for state in states:
        if state.changed_at[:10] <= day.isoformat():
            enabled = bool(state.enabled)
        else:
            break
    return enabled

def schedule_minutes(schedule) -> int:
    if not schedule or schedule.no_pointage:
        return 0
    return calc(schedule.matin_debut, schedule.matin_fin) + calc(schedule.aprem_debut, schedule.aprem_fin)

def exception_for(db: Session, employee_id: str, creche: str, day: datetime.date):
    return db.query(database.ScheduleException).filter(
        database.ScheduleException.employee_id == employee_id,
        database.ScheduleException.creche_nom == creche,
        database.ScheduleException.date == day.isoformat()).first()

def contract_minutes_for_day(db: Session, employee_id: str, creche: str, schedules, day: datetime.date) -> int:
    if not timeclock_enabled_on(db, day, creche):
        return 0
    exceptional = exception_for(db, employee_id, creche, day)
    if exceptional:
        return schedule_minutes(exceptional)
    return schedule_minutes({s.jour: s for s in schedules}.get(day.weekday()))

def month_contract_minutes(schedules, month: int, year: int, db: Session, employee_id: str, creche: str) -> int:
    first = datetime.date(year, month, 1)
    next_month = datetime.date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    last = min(next_month - datetime.timedelta(days=1), datetime.date.today())
    if last < first:
        return 0
    total = 0
    day = first
    while day <= last:
        total += contract_minutes_for_day(db, employee_id, creche, schedules, day)
        day += datetime.timedelta(days=1)
    return total

# ── Auth ───────────────────────────────────────────────────────────────────────

@app.post("/login/")
def login(req: LoginRequest, db: Session = Depends(database.get_db)):
    if req.username == "Administrateur" and req.password == "@dmin:41220*":
        return {"access": "token_admin", "refresh": "none", "role": "ADMIN"}
    creche = db.query(database.Creche).filter(database.Creche.nom == req.username).first()
    if not creche:
        raise HTTPException(status_code=401, detail="Crèche non reconnue.")
    if creche.password != req.password:
        raise HTTPException(status_code=401, detail="Mot de passe incorrect.")
    return {"access": "token_creche", "refresh": "none", "role": "CRECHE",
            "creche": {"id": str(creche.id), "nom": creche.nom}}

@app.get("/admin/settings/timeclock")
def admin_timeclock_status(creche: str = "", db: Session = Depends(database.get_db)):
    return {"enabled": timeclock_enabled(db, creche)}

@app.put("/admin/settings/timeclock")
def admin_set_timeclock(req: TimeclockUpdate, db: Session = Depends(database.get_db)):
    if not req.creche:
        raise HTTPException(400, "La crèche est obligatoire.")
    if timeclock_enabled(db, req.creche) != req.enabled:
        db.add(database.TimeclockState(
            enabled=int(req.enabled),
            changed_at=datetime.datetime.now().isoformat(timespec="seconds"),
            creche_nom=req.creche,
        ))
        db.commit()
    return {"enabled": timeclock_enabled(db, req.creche), "creche": req.creche}

# ── Tablette ───────────────────────────────────────────────────────────────────

@app.get("/timeclock/status")
def timeclock_status(creche: str = "", db: Session = Depends(database.get_db)):
    return {"enabled": timeclock_enabled(db, creche)}

@app.get("/employees/")
def get_employees(creche: str = "", db: Session = Depends(database.get_db)):
    if not creche: return []
    rows = db.query(database.EmployeeCreche).filter(database.EmployeeCreche.creche_nom == creche).all()
    out = []
    for r in rows:
        e = db.query(database.Employee).filter(database.Employee.id == r.employee_id).first()
        if e: out.append({"id": e.id, "nom": e.nom, "prenom": e.prenom})
    return out

@app.post("/sync")
def sync_emargements(emargements: List[EmargementSync], db: Session = Depends(database.get_db)):
    pending = {}
    inserted = 0
    
    for e in emargements:
        if not timeclock_enabled(db, e.creche_name):
            raise HTTPException(status_code=423, detail=f"La pointeuse de {e.creche_name} est désactivée.")
        
        if e.type_event not in ("ARRIVEE", "DEPART"):
            raise HTTPException(status_code=400, detail="Type de signature invalide.")
            
        # 1. On ignore si cette signature exacte a déjà été synchronisée (même ID local)
        if db.query(database.Emargement).filter(database.Emargement.local_id == e.id).first(): 
            continue
            
        day = e.timestamp[:10]
        key = (e.employee_id, day, e.creche_name)
        
        # 2. On vérifie si ce type (ARRIVEE/DEPART) existe déjà pour cet employé aujourd'hui
        existing = db.query(database.Emargement).filter(
            database.Emargement.employee_id == e.employee_id,
            database.Emargement.creche_name == e.creche_name,
            database.Emargement.timestamp.like(f"{day}%")
        ).all()
        
        used_types = {row.type_event for row in existing} | pending.get(key, set())
        
        # 3. LA CORRECTION : Au lieu de crasher (409 Conflict), on ignore le doublon en silence !
        if e.type_event in used_types:
            continue
            
        # 4. C'est un nouvel événement valide, on l'ajoute
        pending.setdefault(key, set()).add(e.type_event)
        
        db.add(database.Emargement(
            local_id=e.id, 
            creche_name=e.creche_name, 
            employee_id=e.employee_id,
            employee_name=e.employee_name, 
            type_event=e.type_event, 
            timestamp=e.timestamp, 
            signature=e.signature
        ))
        inserted += 1
        
    db.commit()
    return {"success": True, "received": len(emargements), "inserted": inserted}
# ── Admin : liste employées avec stats ─────────────────────────────────────────

@app.get("/admin/employees/")
def admin_get_employees(month: int, year: int, db: Session = Depends(database.get_db)):
    month_str = f"{year}-{month:02d}"
    result = []
    for a in db.query(database.EmployeeCreche).all():
        emp = db.query(database.Employee).filter(database.Employee.id == a.employee_id).first()
        if not emp: continue
        scheds = db.query(database.EmployeeSchedule).filter(
            database.EmployeeSchedule.employee_id == emp.id,
            database.EmployeeSchedule.creche_nom == a.creche_nom).all()
        week_mins = sum(schedule_minutes(s) for s in scheds)
        ems = db.query(database.Emargement).filter(
            database.Emargement.employee_id == emp.id,
            database.Emargement.creche_name == a.creche_nom,
            database.Emargement.timestamp.like(f"{month_str}%")).all()
        days = {}
        for e in ems:
            d = e.timestamp[:10]; days.setdefault(d, {}); days[d][e.type_event] = e.timestamp[11:16]
        worked = sum(calc(ev.get("ARRIVEE",""), ev.get("DEPART","")) for ev in days.values() if "ARRIVEE" in ev and "DEPART" in ev)
        contract = month_contract_minutes(scheds, month, year, db, emp.id, a.creche_nom)
        first_schedule = next((s for s in sorted(scheds, key=lambda row: row.jour) if not s.no_pointage and (s.matin_debut or s.aprem_debut)), None)
        result.append({"id": emp.id, "nom": emp.nom, "prenom": emp.prenom, "role": emp.role or "",
            "creche_nom": a.creche_nom,
            "start_time": (first_schedule.matin_debut or first_schedule.aprem_debut) if first_schedule else "",
            "heures_jour_contrat": str(round((week_mins/5)/60, 1)) if week_mins else "0",
            "total_worked_minutes": worked, "total_contract_minutes": contract, "diff_minutes": worked - contract})
    return result

@app.get("/admin/employees/{id}/time/")
def admin_time(id: str, month: int, year: int, creche: str = "", db: Session = Depends(database.get_db)):
    month_str = f"{year}-{month:02d}"
    q = db.query(database.Emargement).filter(database.Emargement.employee_id == id, database.Emargement.timestamp.like(f"{month_str}%"))
    if creche: q = q.filter(database.Emargement.creche_name == creche)
    sq = db.query(database.EmployeeSchedule).filter(database.EmployeeSchedule.employee_id == id)
    if creche: sq = sq.filter(database.EmployeeSchedule.creche_nom == creche)
    sched = {s.jour: s for s in sq.all()}
    days = {}
    for e in q.all(): days.setdefault(e.timestamp[:10], []).append(e)
    daily, tw, tc = [], 0, 0
    for day, evts in sorted(days.items()):
        wd = datetime.datetime.strptime(day, "%Y-%m-%d").weekday()
        current_day = datetime.datetime.strptime(day, "%Y-%m-%d").date()
        cm = contract_minutes_for_day(db, id, creche, list(sched.values()), current_day)
        arr = next((e.timestamp[11:16] for e in evts if e.type_event=="ARRIVEE"), None)
        dep = next((e.timestamp[11:16] for e in evts if e.type_event=="DEPART"), None)
        wm = calc(arr, dep) if arr and dep else 0; ic = bool(arr and dep)
        tw += wm; tc += cm
        daily.append({"date": day, "worked_minutes": wm, "contract_minutes": cm, "diff_minutes": wm-cm, "is_complete": ic, "events_count": len(evts)})
    return {"employee_id": id, "has_schedule": bool(sched), "month": month, "year": year, "daily": daily,
            "total_worked_minutes": tw, "total_contract_minutes": tc, "total_diff_minutes": tw-tc}

@app.get("/admin/employees/{id}/emargements/")
def admin_emarges(id: str, month: int, year: int, creche: str = "", db: Session = Depends(database.get_db)):
    month_str = f"{year}-{month:02d}"
    q = db.query(database.Emargement).filter(database.Emargement.employee_id == id, database.Emargement.timestamp.like(f"{month_str}%"))
    if creche: q = q.filter(database.Emargement.creche_name == creche)
    sq = db.query(database.EmployeeSchedule).filter(database.EmployeeSchedule.employee_id == id)
    if creche: sq = sq.filter(database.EmployeeSchedule.creche_nom == creche)
    sched = {s.jour: s for s in sq.all()}
    result = []
    for e in q.order_by(database.Emargement.timestamp.asc()).all():
        wd = datetime.datetime.strptime(e.timestamp[:10], "%Y-%m-%d").weekday()
        s = sched.get(wd); exp = delay = None
        if s:
            exp = (s.matin_debut or s.aprem_debut) if e.type_event=="ARRIVEE" else (s.aprem_fin or s.matin_fin)
            if exp:
                eh, em2 = map(int, exp.split(":")); ah, am2 = map(int, e.timestamp[11:16].split(":"))
                delay = (ah*60+am2) - (eh*60+em2)
        result.append({"id": str(e.id), "type_event": e.type_event, "horodatage": e.timestamp,
                        "signature": e.signature, "expected_time": exp, "delay_minutes": delay})
    return result

@app.get("/admin/employees/{id}/schedule/")
def admin_get_sched(id: str, creche: str = "", db: Session = Depends(database.get_db)):
    q = db.query(database.EmployeeSchedule).filter(database.EmployeeSchedule.employee_id == id)
    if creche: q = q.filter(database.EmployeeSchedule.creche_nom == creche)
    return [{"jour": s.jour, "matin_debut": s.matin_debut, "matin_fin": s.matin_fin,
             "aprem_debut": s.aprem_debut, "aprem_fin": s.aprem_fin, "no_pointage": bool(s.no_pointage)} for s in q.all()]

@app.post("/admin/employees/{id}/schedule/")
def admin_post_sched(id: str, entries: List[ScheduleEntry], creche: str = "", db: Session = Depends(database.get_db)):
    q = db.query(database.EmployeeSchedule).filter(database.EmployeeSchedule.employee_id == id)
    if creche: q = q.filter(database.EmployeeSchedule.creche_nom == creche)
    q.delete()
    for e in entries:
        db.add(database.EmployeeSchedule(employee_id=id, creche_nom=creche, jour=e.jour,
            matin_debut=e.matin_debut, matin_fin=e.matin_fin, aprem_debut=e.aprem_debut, aprem_fin=e.aprem_fin,
            no_pointage=int(e.no_pointage)))
    db.commit()
    return {"status": "ok"}

@app.get("/admin/employees/{id}/exceptions/")
def admin_get_exceptions(id: str, creche: str = "", db: Session = Depends(database.get_db)):
    q = db.query(database.ScheduleException).filter(database.ScheduleException.employee_id == id)
    if creche: q = q.filter(database.ScheduleException.creche_nom == creche)
    return [{"date": e.date, "label": e.label, "matin_debut": e.matin_debut, "matin_fin": e.matin_fin,
             "aprem_debut": e.aprem_debut, "aprem_fin": e.aprem_fin, "no_pointage": bool(e.no_pointage)}
            for e in q.order_by(database.ScheduleException.date.asc()).all()]

@app.post("/admin/employees/{id}/exceptions/")
def admin_post_exception(id: str, entry: ScheduleExceptionEntry, creche: str = "", db: Session = Depends(database.get_db)):
    if not creche:
        raise HTTPException(400, "La crèche est obligatoire.")
    try:
        datetime.date.fromisoformat(entry.date)
    except ValueError:
        raise HTTPException(400, "Date invalide.")
    existing = db.query(database.ScheduleException).filter(
        database.ScheduleException.employee_id == id, database.ScheduleException.creche_nom == creche,
        database.ScheduleException.date == entry.date).first()
    if existing: db.delete(existing)
    db.add(database.ScheduleException(employee_id=id, creche_nom=creche, date=entry.date, label=entry.label.strip() or "Journée exceptionnelle",
        matin_debut=entry.matin_debut, matin_fin=entry.matin_fin, aprem_debut=entry.aprem_debut, aprem_fin=entry.aprem_fin,
        no_pointage=int(entry.no_pointage)))
    db.commit()
    return {"status": "ok"}

@app.delete("/admin/employees/{id}/exceptions/{date}")
def admin_delete_exception(id: str, date: str, creche: str = "", db: Session = Depends(database.get_db)):
    db.query(database.ScheduleException).filter(database.ScheduleException.employee_id == id,
        database.ScheduleException.creche_nom == creche, database.ScheduleException.date == date).delete()
    db.commit(); return {"status": "ok"}

@app.get("/employees/{id}/balance")
def employee_balance(id: str, creche: str, db: Session = Depends(database.get_db)):
    """Running balance for the tablet; it starts over when the balance returns to zero."""
    schedules = db.query(database.EmployeeSchedule).filter(database.EmployeeSchedule.employee_id == id,
        database.EmployeeSchedule.creche_nom == creche).all()
    events = db.query(database.Emargement).filter(database.Emargement.employee_id == id,
        database.Emargement.creche_name == creche).order_by(database.Emargement.timestamp.asc()).all()
    by_day = {}
    for event in events: by_day.setdefault(event.timestamp[:10], {})[event.type_event] = event.timestamp[11:16]
    if not by_day: return {"diff_minutes": 0}
    balance = 0
    for date, day_events in sorted(by_day.items()):
        day = datetime.date.fromisoformat(date)
        worked = calc(day_events.get("ARRIVEE", ""), day_events.get("DEPART", ""))
        balance += worked - contract_minutes_for_day(db, id, creche, schedules, day)
        if balance == 0: balance = 0
    return {"diff_minutes": balance}

# ── BDD : gestion crèches ──────────────────────────────────────────────────────

@app.get("/admin/db/creches")
def db_creches(db: Session = Depends(database.get_db)):
    return [{"nom": c.nom, "password": c.password} for c in db.query(database.Creche).all()]

@app.post("/admin/db/creches")
def db_add_creche(req: CrecheCreate, db: Session = Depends(database.get_db)):
    if db.query(database.Creche).filter(database.Creche.nom == req.nom).first():
        raise HTTPException(400, "Cette crèche existe déjà.")
    db.add(database.Creche(nom=req.nom, password=req.password)); db.commit()
    return {"status": "ok"}

@app.put("/admin/db/creches/{nom}")
def db_upd_creche(nom: str, req: CrecheUpdate, db: Session = Depends(database.get_db)):
    c = db.query(database.Creche).filter(database.Creche.nom == nom).first()
    if not c: raise HTTPException(404, "Crèche non trouvée.")
    c.password = req.password; db.commit(); return {"status": "ok"}

@app.delete("/admin/db/creches/{nom}")
def db_del_creche(nom: str, db: Session = Depends(database.get_db)):
    db.query(database.EmployeeCreche).filter(database.EmployeeCreche.creche_nom == nom).delete()
    db.query(database.EmployeeSchedule).filter(database.EmployeeSchedule.creche_nom == nom).delete()
    db.query(database.Creche).filter(database.Creche.nom == nom).delete()
    db.commit(); return {"status": "ok"}

# ── BDD : gestion employées ────────────────────────────────────────────────────

@app.get("/admin/db/employees")
def db_employees(db: Session = Depends(database.get_db)):
    out = []
    for emp in db.query(database.Employee).all():
        creches = [a.creche_nom for a in db.query(database.EmployeeCreche).filter(database.EmployeeCreche.employee_id == emp.id).all()]
        out.append({"id": emp.id, "nom": emp.nom, "prenom": emp.prenom, "role": emp.role or "", "creches": creches})
    return out

@app.post("/admin/db/employees")
def db_add_emp(req: EmployeeCreate, db: Session = Depends(database.get_db)):
    emp = database.Employee(id=str(uuid.uuid4()), nom=req.nom.strip(), prenom=req.prenom.strip(), role=req.role.strip())
    db.add(emp); db.commit()
    return {"id": emp.id, "nom": emp.nom, "prenom": emp.prenom, "role": emp.role}

@app.put("/admin/db/employees/{id}")
def db_upd_emp(id: str, req: EmployeeCreate, db: Session = Depends(database.get_db)):
    emp = db.query(database.Employee).filter(database.Employee.id == id).first()
    if not emp: raise HTTPException(404, "Employée non trouvée.")
    emp.nom = req.nom.strip(); emp.prenom = req.prenom.strip(); emp.role = req.role.strip()
    db.commit(); return {"status": "ok"}

@app.delete("/admin/db/employees/{id}")
def db_del_emp(id: str, db: Session = Depends(database.get_db)):
    db.query(database.EmployeeCreche).filter(database.EmployeeCreche.employee_id == id).delete()
    db.query(database.EmployeeSchedule).filter(database.EmployeeSchedule.employee_id == id).delete()
    db.query(database.Employee).filter(database.Employee.id == id).delete()
    db.commit(); return {"status": "ok"}

# ── BDD : affectations ─────────────────────────────────────────────────────────

@app.post("/admin/db/assignments")
def db_add_assign(req: AssignmentCreate, db: Session = Depends(database.get_db)):
    if db.query(database.EmployeeCreche).filter(
            database.EmployeeCreche.employee_id == req.employee_id,
            database.EmployeeCreche.creche_nom == req.creche_nom).first():
        raise HTTPException(400, "Déjà affectée à cette crèche.")
    db.add(database.EmployeeCreche(employee_id=req.employee_id, creche_nom=req.creche_nom))
    db.commit(); return {"status": "ok"}

@app.delete("/admin/db/assignments/{employee_id}/{creche_nom}")
def db_del_assign(employee_id: str, creche_nom: str, db: Session = Depends(database.get_db)):
    db.query(database.EmployeeCreche).filter(
        database.EmployeeCreche.employee_id == employee_id,
        database.EmployeeCreche.creche_nom == creche_nom).delete()
    db.commit(); return {"status": "ok"}

# ── Seed ADDITIF : n'écrase jamais les données existantes ─────────────────────

@app.post("/admin/seed")
def seed(db: Session = Depends(database.get_db)):
    added_c = added_e = added_a = added_s = 0

    # Crèches
    creches_data = [
        ("Les_coccinelles_de_Dhuizon", "Dhuizon41220/"),
        ("L_écopain_de_Neung", "Neung41210/"),
        ("La_Barbotine", "Jouy45370/"),
        ("Quint_et_Sens", "LaFerté45240/")
    ]
    for nom, pwd in creches_data:
        if not db.query(database.Creche).filter(database.Creche.nom == nom).first():
            db.add(database.Creche(nom=nom, password=pwd)); added_c += 1

    # Employées
    seed_emps = [
        ("CLAUZEL", "Johanna", "Directrice"),
        ("FOUCAULT", "Sophie", "CAP Petite Enfance"),
        ("GOUJON", "Céline", "Assistante maternelle"),
        ("MICHELIN-POITRINEAU", "Margaux", "CAP Petite Enfance"),
        ("CLAUZEL", "Manon", "Éducatrice de jeune enfant"),
        ("ALGISI", "Nathalie", "CAP Petite Enfance"),
        ("TALBOT", "Laura", "Auxiliaire de puériculture"),
        ("MOREL", "Mélanie", "CAP Petite Enfance"),
        ("PIFRE", "Marie", "Éducatrice de jeune enfant"),
        ("JOUBEL", "Flora", "Auxiliaire de puériculture"),
        ("TANGUY", "Stécy", "Auxiliaire de puériculture"),
        ("LECONTE", "Wendy", "CAP Petite Enfance"),
        ("HILAIRE", "Ophélie", "Auxiliaire de puériculture"),
        ("VINCHON", "Anne-Cécile", "Éducatrice de jeune enfant"),
        ("ROCCA", "Ketty", "Auxiliaire de puériculture"),
        ("RICHALET", "Lilou", "CAP Petite Enfance"),
        ("LECONTE", "Jennifer", "CAP Petite Enfance")
    ]
    emp_ids = {}
    for nom, prenom, role in seed_emps:
        ex = db.query(database.Employee).filter(database.Employee.nom == nom, database.Employee.prenom == prenom).first()
        if ex:
            emp_ids[f"{prenom} {nom}"] = ex.id
        else:
            eid = str(uuid.uuid4())
            db.add(database.Employee(id=eid, nom=nom, prenom=prenom, role=role))
            emp_ids[f"{prenom} {nom}"] = eid; added_e += 1
    db.flush()

    # Affectations
    assigns = [
        ("Johanna CLAUZEL", "Les_coccinelles_de_Dhuizon"),
        ("Sophie FOUCAULT", "Les_coccinelles_de_Dhuizon"),
        ("Céline GOUJON", "Les_coccinelles_de_Dhuizon"),
        ("Margaux MICHELIN-POITRINEAU", "Les_coccinelles_de_Dhuizon"),
        
        ("Manon CLAUZEL", "L_écopain_de_Neung"),
        ("Nathalie ALGISI", "L_écopain_de_Neung"),
        ("Laura TALBOT", "L_écopain_de_Neung"),
        ("Mélanie MOREL", "L_écopain_de_Neung"),
        ("Margaux MICHELIN-POITRINEAU", "L_écopain_de_Neung"),

        ("Marie PIFRE", "Quint_et_Sens"),
        ("Flora JOUBEL", "Quint_et_Sens"),
        ("Stécy TANGUY", "Quint_et_Sens"),
        ("Wendy LECONTE", "Quint_et_Sens"),
        ("Margaux MICHELIN-POITRINEAU", "Quint_et_Sens"),
        ("Ophélie HILAIRE", "Quint_et_Sens"),

        ("Anne-Cécile VINCHON", "La_Barbotine"),
        ("Ketty ROCCA", "La_Barbotine"),
        ("Lilou RICHALET", "La_Barbotine"),
        ("Jennifer LECONTE", "La_Barbotine"),
        ("Ophélie HILAIRE", "La_Barbotine"),
        ("Margaux MICHELIN-POITRINEAU", "La_Barbotine")
    ]
    for ename, cnom in assigns:
        eid = emp_ids.get(ename)
        if not eid: continue
        if not db.query(database.Creche).filter(database.Creche.nom == cnom).first(): continue
        
        # Add assignment
        if not db.query(database.EmployeeCreche).filter(
                database.EmployeeCreche.employee_id == eid,
                database.EmployeeCreche.creche_nom == cnom).first():
            db.add(database.EmployeeCreche(employee_id=eid, creche_nom=cnom)); added_a += 1
            
            # Add default schedule (Monday to Friday, 8h to 19h)
            for jour in range(5): # 0 to 4
                db.add(database.EmployeeSchedule(
                    employee_id=eid, creche_nom=cnom, jour=jour,
                    matin_debut="08:00", matin_fin="12:00",
                    aprem_debut="12:00", aprem_fin="19:00"
                ))
            added_s += 1

    db.commit()
    return {"status": "ok", "message": f"Ajouté : {added_c} crèches, {added_e} employées, {added_a} affectations, {added_s} emplois du temps."}

# ── Dashboard HTML ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="dashboard.html", context={})
