import datetime

from django.test import TestCase
from django.utils import timezone, formats
from django.core.exceptions import ValidationError

from scarlet.versioning.models import published_signal, BaseModel, VersionModel

import models


class ModelTests(TestCase):
    fixtures = ('test_data.json', )

    def _check_different_book_versions(self, bd, bp):
        self.assertTrue(bd.pk != bp.pk)
        bd_reviews = list(bd.review_set.all())
        bp_reviews = list(bp.review_set.all())
        bp_gallery = list(bp.galleries.all())
        bd_gallery = list(bd.galleries.all())
        self.assertEqual(len(bp_gallery), len(bd_gallery))
        self.assertEqual(len(bp_reviews), len(bd_reviews))

        bd_reviews[0].text = 'changed'
        bd_reviews[0].save()

        bd_gallery[0].name = 'changed'
        bd_gallery[0].save()

        self.assertTrue(models.Review.objects.filter(book=bd.pk, text='changed').exists())
        self.assertFalse(models.Review.objects.filter(book=bp.pk, text='changed').exists())

        self.assertTrue(models.Gallery.objects.filter(book=bd.pk, name='changed').exists())
        self.assertFalse(models.Gallery.objects.filter(book=bp.pk, name='changed').exists())

    def testBadModel(self):
        """
        need to define _base_model in Meta, its value should be a subclass
        of BaseModel
        """
        Base = type('Base', (BaseModel, ), {'__module__': __name__})
        # good
        Meta = type('Meta', (), {'_base_model': Base})
        type('O1', (VersionModel, ), {'Meta': Meta, '__module__': __name__})

        # bad
        try:
            type('O2', (VersionModel, ), {'Meta': Meta, '__module__': __name__})
        except:
            self.assertRaises(TypeError)

    def testNew(self):
        a = models.Author(name='straight')
        a.save()
        self.assertTrue(models.AuthorBase.objects.filter(pk=a.object_id).exists())

    def testGetVersion(self):
        a = models.AuthorBase.objects.get(pk=1)
        self.assertEqual(a.get_version(state=models.Author.PUBLISHED), None)

        v = a.get_version(state=models.Author.DRAFT)
        self.assertEqual(v.name, 'test')

        v.publish()

        # Now returns
        self.assertEqual(a.get_version(date=timezone.now()), v)

        # Too old returns none
        self.assertEqual(a.get_version(date=a.created_date), None)

    def testPublishedSignal(self):
        book = models.Book.objects.get(pk=1)
        self.name = None

        # define the local listener
        def published_listener(sender, instance, **kwargs):
            self.name = instance.name

        # connect & send the signal
        published_signal.connect(published_listener)
        book.publish()
        self.assertEqual(self.name, book.name)
        base_book = models.BookBase.objects.get(pk=1)
        self.assertEqual(book.last_scheduled, base_book.v_last_save)

    def testPublishedFutureNoSignal(self):
        book = models.Book.objects.get(pk=1)

        # define the local listener
        def published_listener(sender, instance, **kwargs):
            assert False, "Should not have been called"

        # connect & send the signal
        published_signal.connect(published_listener)
        book.publish(when=timezone.now() + datetime.timedelta(hours=1))
        self.assertTrue(book.state, models.Book.SCHEDULED)

        base_book = models.BookBase.objects.get(pk=1)
        self.assertFalse(book.last_scheduled == base_book.v_last_save)
        self.assertTrue(models.Book.objects.filter(object_id=book.object_id,
                                                   state=models.Book.SCHEDULED).exists())
        self.assertFalse(models.Book.objects.filter(object_id=book.object_id,
                                                    state=models.Book.PUBLISHED).exists())

    def testPublishAuthor(self):
        author = models.Author.objects.get(name='test')
        author.publish()

        ad = models.Author.objects.get(object_id=author.object_id, state=models.Author.DRAFT)
        ap = models.Author.objects.get(object_id=author.object_id, state=models.Author.PUBLISHED)

        self.assertTrue(ad.pk != ap.pk)

        # M2m is copied
        self.assertEqual(list(ap.associates.all()), [models.AuthorBase(pk=2)])
        self.assertEqual(list(ad.associates.all()), [models.AuthorBase(pk=2)])

        # M2M changes are isolated
        ab = models.AuthorBase.objects.get(pk=1)
        ad.associates.add(ab)
        self.assertEqual(list(ap.associates.all()), [models.AuthorBase(pk=2)])
        self.assertEqual(
            list(ad.associates.all()),
            [models.AuthorBase(pk=2), models.AuthorBase(pk=1)])

    def testPublishBook(self):
        book = models.Book.objects.get(pk=1)

        book.publish()

        bd = models.Book.objects.get(object_id=book.object_id, state=models.Author.DRAFT)
        bp = models.Book.objects.get(object_id=book.object_id, state=models.Author.PUBLISHED)
        self._check_different_book_versions(bd, bp)

    def testMakeDraftBook(self):
        book = models.Book.objects.get(pk=1)
        self.assertEqual(book.name, 'Book1')
        book.publish()

        # Change the draft
        odb = models.BookBase.objects.get(pk=1).get_version(state=models.Book.DRAFT)
        self.assertEqual(odb.last_scheduled, odb.last_save)
        odb.name = 'book2'
        odb.save()
        self.assertTrue(models.Book.objects.filter(name='book2').exists())

        # Check last scheduled
        self.assertEqual(odb.last_scheduled, book.last_scheduled)
        self.assertTrue(odb.last_scheduled < odb.last_save)

        # Make the current published a draft
        opb = models.BookBase.objects.get(pk=1).get_version(state=models.Book.PUBLISHED)
        opb.make_draft()

        db = models.BookBase.objects.get(pk=1).get_version(state=models.Book.DRAFT)
        pb = models.BookBase.objects.get(pk=1).get_version(state=models.Book.PUBLISHED)

        # Check everything changed, properly
        # new draft is the old published
        self.assertEqual(db.pk, opb.pk)
        # but there is a new published
        self.assertTrue(db.pk != pb.pk)
        # the new draft is not the same as the old draft
        self.assertTrue(db.pk != odb.pk)
        # name was restored
        self.assertEqual(db.name, 'Book1')

        self.assertEqual(db.last_scheduled, pb.last_scheduled)
        self.assertEqual(db.last_scheduled, db.last_save)

        # Old draft is gone
        self.assertFalse(models.Book.objects.filter(name='book2').exists())
        self._check_different_book_versions(db, pb)

    def testDeleteRelated(self):
        book = models.Book.objects.get(pk=1)
        rs = list(book.review_set.all())
        gs = list(book.galleries.all())

        book.publish()

        bp = models.Book.objects.get(object_id=book.object_id, state=models.Author.PUBLISHED)

        self.assertEqual(models.Review.objects.all().count(), 4)
        self.assertEqual(models.Gallery.objects.all().count(), 4)

        # After delete only orginal remains
        bp.delete()
        book = models.Book.objects.get(pk=1)
        self.assertEqual(models.Review.objects.all().count(), 2)
        self.assertEqual(models.Gallery.objects.all().count(), 2)
        self.assertEqual(list(book.review_set.all()), rs)
        self.assertEqual(list(book.galleries.all()), gs)

    def testDeleteNotRelated(self):
        store = models.Store.objects.get(pk=1)
        store.publish()
        sp = models.Store.objects.get(object_id=1, state=models.Store.PUBLISHED)
        self.assertEqual(list(sp.books.all()), [models.BookBase(pk=1)])

        # After deletion the book still exists
        sp.delete()
        self.assertTrue(models.BookBase.objects.filter(pk=1).exists())
        self.assertEqual(len(models.Store.objects.all()), 1)

    def testVersionedUnique(self):
        """
        use versioned_unique to force unique on field value
        """
        self.assertFalse(hasattr(models.Author, 'versioned_unique'))
        setattr(models.Author, 'versioned_unique', ['name'])
        self.assertEqual(models.Author.versioned_unique, ['name'])
        a1 = models.Author.objects.get(vid=1)

        # should fail on second(duplicate) instance
        a2 = models.Author(name=a1.name)
        with self.assertRaises(ValidationError):
            a2.validate_unique()

        # multiple versions are not affected (can co-exists)
        a3 = models.Author(object=a1.object, name=a1.name)
        a3.validate_unique()

    def testStatus1(self):
        book = models.Book.objects.get(vid=1)
        self.assertEqual(book.state, models.Book.DRAFT)
        self.assertEqual(book.status_line(), "Draft saved: 08/30/2012")

        # schedule to publish in future. should get status as Scheduled.
        future = timezone.now() + datetime.timedelta(days=7)
        book.publish(when=future)
        draft = models.Book.objects.get(vid=1)

        self.assertEqual(draft.last_save, draft.last_scheduled)
        self.assertEqual(draft.v_last_save, None)  # v_last_save empty
        status = "%s: %s" % ('Publish Scheduled', formats.date_format(draft.date_published,
                                                                      "SHORT_DATE_FORMAT"))
        self.assertEqual(status, draft.status_line())

        # publish it now. should get status as Published
        when = timezone.now()
        book = models.Book.objects.get(vid=1)
        book.publish(when=when)
        draft2 = models.Book.objects.get(vid=1)

        self.assertEqual(draft2.last_save, draft2.last_scheduled)
        self.assertEqual(draft2.last_save, draft2.v_last_save)
        status = "%s: %s" % ('Published', formats.date_format(draft2.date_published,
                                                              "SHORT_DATE_FORMAT"))
        self.assertEqual(status, draft2.status_line())
        self.assertEqual(draft2.date_published, when)

        # schedule to publish in future again. should get status as Scheduled
        book = models.Book.objects.get(vid=1)
        future = timezone.now() + datetime.timedelta(days=20)
        book.publish(when=future)
        draft = models.Book.objects.get(vid=1)
        self.assertEqual(draft.last_save, draft.last_scheduled)
        self.assertTrue(draft.last_scheduled > draft.v_last_save)
        status = "%s: %s" % ('Publish Scheduled', formats.date_format(draft.date_published,
                                                                      "SHORT_DATE_FORMAT"))
        self.assertEqual(status, draft.status_line())

    def testStatus2(self):
        book = models.Book.objects.get(vid=1)
        self.assertEqual(book.state, models.Book.DRAFT)
        self.assertEqual(book.status_line(), "Draft saved: 08/30/2012")

        book.publish()

        book = models.Book.objects.get(object_id=book.object_id, state=models.Book.PUBLISHED)
        draft = models.Book.objects.get(vid=1, state=models.Book.DRAFT)
        self.assertEqual(book.v_last_save, draft.v_last_save)
        self.assertEqual(draft.last_save, draft.last_scheduled)
        self.assertEqual(draft.last_save, draft.v_last_save)
        status = "%s: %s" % ('Published', formats.date_format(draft.last_save,
                                                              "SHORT_DATE_FORMAT"))
        self.assertEqual(status, book.status_line())
