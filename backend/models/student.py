from mongoengine import Document, StringField, FloatField


class Student(Document):
    enrollment = StringField(required=True, unique=True)
    name = StringField(required=True)
    email = StringField(required=True)
    phone = StringField(required=True)
    course = StringField(required=True)
    branch = StringField(required=True)
    class_assigned = StringField(required=True)
    pending_fees = FloatField(default=0) 
    password = StringField(required=True)
