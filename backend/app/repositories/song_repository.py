from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.entities import Song


class SongRepository:
    def __init__(self, db: Session, teacher_id: int | None = None):
        self.db = db
        self.teacher_id = teacher_id

    def _visible(self):
        if self.teacher_id is None:
            return Song.owner_teacher_id.is_(None)
        return or_(Song.owner_teacher_id.is_(None), Song.owner_teacher_id == self.teacher_id)

    def get(self, song_id: int) -> Song | None:
        return self.db.scalar(select(Song).where(Song.id == song_id, self._visible()))

    def list_songs(
        self, region: str | None = None, province: str | None = None, grade: str | None = None
    ) -> list[Song]:
        statement = select(Song).where(self._visible())
        if region:
            statement = statement.where(Song.region == region)
        if province:
            statement = statement.where(Song.province == province)
        if grade:
            statement = statement.where(Song.grade == grade)
        return list(self.db.scalars(statement.order_by(Song.region, Song.source_row, Song.id)).all())

    def search_by_name(self, name: str) -> list[Song]:
        return list(
            self.db.scalars(select(Song).where(self._visible(), Song.name.contains(name)).order_by(Song.id).limit(20)).all()
        )
