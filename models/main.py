from peewee import *

db = SqliteDatabase("main.db")


class User(Model):
    email = CharField(unique=True)
    name = CharField()
    picture = CharField()

    class Meta:
        database = db


class Session(Model):
    user = ForeignKeyField(User, backref="sessions")
    token = CharField()
    refresh_token = CharField()
    access_token = CharField()

    class Meta:
        database = db


class Index(Model):
    user = ForeignKeyField(User, backref="indices")
    name = CharField()
    link = CharField()

    class Meta:
        database = db


def init():
    db.connect()
    db.create_tables([User, Session, Index], safe=True)
