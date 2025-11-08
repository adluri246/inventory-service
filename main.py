from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

# --- Database Setup ---
DATABASE_URL = "sqlite:///database.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()

# --- Models ---
class Grocery(Base):
    __tablename__ = "groceries"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    threshold = Column(Float, default=0)
    quantity = relationship("Quantity", back_populates="grocery", uselist=False)
    history = relationship("History", back_populates="grocery")

class Quantity(Base):
    __tablename__ = "quantities"
    id = Column(Integer, primary_key=True, index=True)
    grocery_id = Column(Integer, ForeignKey("groceries.id"))
    quantity = Column(Float, default=0)
    grocery = relationship("Grocery", back_populates="quantity")

class History(Base):
    __tablename__ = "history"
    id = Column(Integer, primary_key=True, index=True)
    grocery_id = Column(Integer, ForeignKey("groceries.id"))
    change = Column(Float)
    action = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)
    grocery = relationship("Grocery", back_populates="history")

Base.metadata.create_all(bind=engine)

# --- Schemas ---
class GroceryCreate(BaseModel):
    name: str
    threshold: float

class GroceryUpdate(BaseModel):
    name: str | None = None
    threshold: float | None = None

class QuantityUpdate(BaseModel):
    grocery_id: int
    change: float  # positive for addition, negative for removal

# --- App Init ---
app = FastAPI(title="Grocery Inventory Management")

# --- Utility ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Routes ---

@app.post("/groceries")
def create_grocery(item: GroceryCreate):
    db = SessionLocal()
    existing = db.query(Grocery).filter_by(name=item.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Grocery already exists")
    grocery = Grocery(name=item.name, threshold=item.threshold)
    db.add(grocery)
    db.commit()
    db.refresh(grocery)
    quantity = Quantity(grocery_id=grocery.id, quantity=0)
    db.add(quantity)
    db.commit()
    db.close()
    return {"message": "Grocery added successfully", "grocery": grocery.name}

@app.get("/groceries")
def list_groceries():
    db = SessionLocal()
    groceries = db.query(Grocery).all()
    result = []
    for g in groceries:
        qty = g.quantity.quantity if g.quantity else 0
        result.append({
            "id": g.id,
            "name": g.name,
            "threshold": g.threshold,
            "quantity": qty
        })
    db.close()
    return result

@app.put("/groceries/{grocery_id}")
def update_grocery(grocery_id: int, item: GroceryUpdate):
    db = SessionLocal()
    grocery = db.query(Grocery).filter_by(id=grocery_id).first()
    if not grocery:
        raise HTTPException(status_code=404, detail="Grocery not found")
    if item.name:
        grocery.name = item.name
    if item.threshold is not None:
        grocery.threshold = item.threshold
    db.commit()
    db.close()
    return {"message": "Grocery updated successfully"}

@app.delete("/groceries/{grocery_id}")
def delete_grocery(grocery_id: int):
    db = SessionLocal()
    grocery = db.query(Grocery).filter_by(id=grocery_id).first()
    if not grocery:
        raise HTTPException(status_code=404, detail="Grocery not found")
    db.delete(grocery)
    db.commit()
    db.close()
    return {"message": "Grocery deleted successfully"}

@app.post("/quantities/update")
def update_quantity(update: QuantityUpdate):
    db = SessionLocal()
    qty = db.query(Quantity).filter_by(grocery_id=update.grocery_id).first()
    grocery = db.query(Grocery).filter_by(id=update.grocery_id).first()
    if not grocery:
        raise HTTPException(status_code=404, detail="Grocery not found")

    qty.quantity += update.change
    action = "added" if update.change > 0 else "removed"
    history = History(grocery_id=grocery.id, change=update.change, action=action)
    db.add(history)
    db.commit()

    db.refresh(qty)
    result = {
        "grocery": grocery.name,
        "new_quantity": qty.quantity,
        "below_threshold": qty.quantity < grocery.threshold
    }
    db.close()
    return result

@app.get("/quantities")
def get_quantities():
    db = SessionLocal()
    items = db.query(Grocery).all()
    result = [{"name": g.name, "quantity": g.quantity.quantity if g.quantity else 0} for g in items]
    db.close()
    return result

@app.get("/alerts")
def get_alerts():
    db = SessionLocal()
    groceries = db.query(Grocery).all()
    alerts = []
    for g in groceries:
        if g.quantity and g.quantity.quantity < g.threshold:
            alerts.append({
                "grocery": g.name,
                "quantity": g.quantity.quantity,
                "threshold": g.threshold,
                "status": "Below Threshold"
            })
    db.close()
    return alerts

@app.get("/history")
def get_history():
    db = SessionLocal()
    history = db.query(History).order_by(History.timestamp.desc()).all()
    result = [{
        "grocery": h.grocery.name,
        "change": h.change,
        "action": h.action,
        "timestamp": h.timestamp
    } for h in history]
    db.close()
    return result
