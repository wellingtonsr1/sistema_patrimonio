from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.location import Location
from app.models.asset import Asset
from app.schemas.location import LocationCreate, LocationUpdate


class LocationService:
    @staticmethod
    def get_all(db: Session) -> List[Location]:
        return db.query(Location).order_by(Location.branch, Location.department, Location.name).all()

    @staticmethod
    def get_by_id(db: Session, location_id: int) -> Optional[Location]:
        return db.query(Location).filter(Location.id == location_id).first()

    @staticmethod
    def get_by_name(db: Session, name: str) -> Optional[Location]:
        return db.query(Location).filter(Location.name == name).first()

    @staticmethod
    def create(db: Session, data: LocationCreate) -> Location:
        if LocationService.get_by_name(db, data.name):
            raise ValueError("Já existe um local cadastrado com este nome")

        location = Location(
            name=data.name,
            branch=data.branch,
            building=data.building,
            floor=data.floor,
            room=data.room,
            department=data.department,
            manager_name=data.manager_name,
            description=data.description,
        )
        db.add(location)
        db.commit()
        db.refresh(location)
        return location

    @staticmethod
    def update(db: Session, location_id: int, data: LocationUpdate) -> Optional[Location]:
        location = LocationService.get_by_id(db, location_id)
        if not location:
            return None

        if data.name is not None and data.name != location.name:
            if LocationService.get_by_name(db, data.name):
                raise ValueError("Já existe um local cadastrado com este nome")

        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(location, key, value)
            
        db.commit()
        db.refresh(location)
        return location

    @staticmethod
    def count_assets(db: Session, location_id: int) -> int:
        return db.query(func.count(Asset.id)).filter(Asset.location_id == location_id).scalar() or 0
