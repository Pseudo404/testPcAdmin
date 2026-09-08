from sqlalchemy import create_engine, Column, Integer, String, Text, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "sqlite:///./sync_database.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Creche(Base):
    __tablename__ = "creches"
    id = Column(Integer, primary_key=True, index=True)
    nom = Column(String, unique=True, index=True)
    password = Column(String)

class Employee(Base):
    __tablename__ = "employees"
    id = Column(String, primary_key=True, index=True)
    nom = Column(String)
    prenom = Column(String)
    role = Column(String, default="")

class EmployeeCreche(Base):
    """Jonction : un employé peut être dans plusieurs crèches."""
    __tablename__ = "employee_creches"
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(String, index=True)
    creche_nom = Column(String, index=True)

class EmployeeSchedule(Base):
    """Emploi du temps par employé ET par crèche."""
    __tablename__ = "employee_schedules"
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(String, index=True)
    creche_nom = Column(String, index=True)
    jour = Column(Integer)
    matin_debut = Column(String, default="")
    matin_fin = Column(String, default="")
    aprem_debut = Column(String, default="")
    aprem_fin = Column(String, default="")
    # Le jour est bien planifié, mais aucune signature n'est attendue (week-end,
    # fermeture, récupération…).
    no_pointage = Column(Integer, nullable=False, default=0)

class ScheduleException(Base):
    """Horaire ponctuel qui remplace la grille hebdomadaire (formation, etc.)."""
    __tablename__ = "schedule_exceptions"
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(String, index=True)
    creche_nom = Column(String, index=True)
    date = Column(String, index=True)
    label = Column(String, default="Journée exceptionnelle")
    matin_debut = Column(String, default="")
    matin_fin = Column(String, default="")
    aprem_debut = Column(String, default="")
    aprem_fin = Column(String, default="")
    no_pointage = Column(Integer, nullable=False, default=0)

class Emargement(Base):
    __tablename__ = "emargements"
    id = Column(Integer, primary_key=True, index=True)
    local_id = Column(String, unique=True, index=True)
    creche_name = Column(String, index=True)
    employee_id = Column(String, index=True)
    employee_name = Column(String)
    type_event = Column(String)
    timestamp = Column(String)
    signature = Column(Text)

class TimeclockState(Base):
    """Historique des activations pour exclure les congés du calcul contractuel."""
    __tablename__ = "timeclock_states"
    id = Column(Integer, primary_key=True, index=True)
    enabled = Column(Integer, nullable=False, default=0)
    changed_at = Column(String, nullable=False)
    creche_nom = Column(String, index=True, nullable=True)

Base.metadata.create_all(bind=engine)

# Migration automatique : ajoute les colonnes des versions précédentes.
def _migrate():
    with engine.connect() as conn:
        insp = inspect(engine)
        if "employees" in insp.get_table_names():
            cols = [c["name"] for c in insp.get_columns("employees")]
            if "role" not in cols:
                conn.execute(text("ALTER TABLE employees ADD COLUMN role TEXT DEFAULT ''"))
        if "employee_schedules" in insp.get_table_names():
            cols = [c["name"] for c in insp.get_columns("employee_schedules")]
            if "no_pointage" not in cols:
                conn.execute(text("ALTER TABLE employee_schedules ADD COLUMN no_pointage INTEGER NOT NULL DEFAULT 0"))
        if "timeclock_states" in insp.get_table_names():
            cols = [c["name"] for c in insp.get_columns("timeclock_states")]
            if "creche_nom" not in cols:
                conn.execute(text("ALTER TABLE timeclock_states ADD COLUMN creche_nom TEXT"))
        conn.commit()

_migrate()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
