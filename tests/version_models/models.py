from django.db import models

from scarlet.versioning import fields
from scarlet.versioning.models import VersionView, Cloneable, BaseModel, BaseVersionedModel


class Harmless(object):
    is_harmless = True


class ConcreteModel(models.Model):
    name = models.CharField(max_length=255)


class NameModel(models.Model):
    name = models.CharField(max_length=255)

    class Meta:
        abstract = True


class Abstract(BaseVersionedModel, NameModel):
    associates = fields.M2MFromVersion('self', blank=True)

    class Meta:
        abstract = True


class AbstractM2MBook(models.Model):
    books = fields.M2MFromVersion('Book', blank=True)
    cartoon = fields.FKToVersion('Cartoon', blank=True, null=True)

    class Meta:
        abstract = True


class Author(VersionView, Abstract):
    def __unicode__(self):
        return self.name


class Book(VersionView, NameModel, Harmless):
    _clone_related = ['review', 'galleries']

    author = models.ForeignKey(Author)
    galleries = fields.M2MFromVersion('Gallery')

    def __unicode__(self):
        return self.name


class BookNoRelated(VersionView, NameModel, Harmless):
    author = models.ForeignKey(Author)
    galleries = fields.M2MFromVersion('Gallery')

    def __unicode__(self):
        return self.name


class Review(Cloneable):
    book = fields.FKToVersion(Book)
    text = models.CharField(max_length=255)

    def __unicode__(self):
        return self.text


class Store(VersionView, NameModel, AbstractM2MBook):
    pass


class Gallery(Cloneable):
    name = models.CharField(max_length=255)

    def __unicode__(self):
        return self.name


class NoReverse(VersionView, NameModel):
    _clone_related = ('rm2m', )


class RM2M(Cloneable):
    no = models.ManyToManyField(NoReverse)


class Cartoon(VersionView, NameModel):
    author = models.ForeignKey(Author,
                               related_name="works",
                               blank=True,
                               null=True,
                               on_delete=models.SET_NULL)

    def __unicode__(self):
        return self.name


class Image(Cloneable):
    name = models.CharField(max_length=255)
    cartoons = models.ManyToManyField(Cartoon)

    def __unicode__(self):
        return self.name


class CustomModel(BaseModel):
    reg_number = models.CharField(max_length=20)


class Gun(VersionView):
    name = models.CharField(max_length=20)

    class Meta:
        _base_model = CustomModel
