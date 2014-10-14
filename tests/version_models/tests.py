import unittest
import datetime

from django.test import TestCase, TransactionTestCase
from django.utils import timezone, formats
from django.core.exceptions import ValidationError
from django.db import models as dbmodels

from scarlet.versioning.models import VersionView
from scarlet.versioning import manager

import models

class ModelStructureTests(unittest.TestCase):

    def testCopyAttrs(self):
        O1 = type('C1', (VersionView,), {"__module__": __name__,
                                         "new_attr": "something"})
        o = O1()
        self.assertFalse(hasattr(o._meta._version_model, 'new_attr'))

        O2 = type('C2', (VersionView,), {"__module__": __name__,
                                         "new_attr": "something",
                                         "_copy_extra_attrs": ['new_attr']})
        o2 = O2()
        self.assertTrue(hasattr(o2._meta._version_model, 'new_attr'))
        self.assertEqual(o2._meta._version_model.new_attr, 'something')

    def testCustomBadBaseModel(self):
        """
        _base_model should be a subclass of BaseModel
        """

        with self.assertRaises(AssertionError):
            class BadCustomModel(dbmodels.Model):
                reg_number = dbmodels.CharField(max_length=20)

            class BadGun(VersionView):
                name = dbmodels.CharField(max_length=20)

                class Meta:
                    _base_model = BadCustomModel

    def testNoConcreteModels(self):
        """
        Version Views can't inherit from concrete models
        """

        with self.assertRaises(TypeError):
            class Bad(VersionView, models.ConcreteModel):
                test = dbmodels.CharField(max_length=20)

    def testTooManyBaseVersionedModels(self):
        class V1(models.BaseVersionedModel):
            name = dbmodels.CharField(max_length=255)
            class Meta:
                abstract = True

        class V2(models.BaseVersionedModel):
            code = dbmodels.CharField(max_length=255)
            class Meta:
                abstract = True

        with self.assertRaises(TypeError):
            class BadBases(VersionView, V1, V2):
                test = dbmodels.CharField(max_length=20)


    def testM2MOnVersioned(self):
        with self.assertRaises(TypeError):
            class BadM2M(VersionView):
                m2 = dbmodels.ManyToManyField('Author')

    def testNoBaseModel(self):
        with self.assertRaises(TypeError):
            class BadBase(VersionView, models.BaseModel):
                name = dbmodels.CharField(max_length=255)

class ModelTests(TestCase):
    fixtures = ('test_data.json',)

    def setUp(self):
        manager.activate('draft')

    def tearDown(self):
        manager.deactivate()

    def _check_different_book_versions(self, bd, bp):
        self.assertEqual(bd.object_id, bp.object_id)
        self.assertEqual(bd.id, bp.id)
        self.assertEqual(bd.pk, bp.pk)
        self.assertNotEqual(bd.vid, bp.vid)

    def _prepare_books(self):
        book = models.Book.objects.get(vid=1)
        book.publish()

        with manager.SwitchSchema('published'):
            bp = models.Book.normal.get(object_id=book.object_id)
        with manager.SwitchSchema('draft'):
            bd = models.Book.normal.get(object_id=book.object_id)

        return bp, bd

    def testFieldMap(self):
        book = models.Book.objects.get(pk=1)
        map1 = book._get_field_map()

        delattr(book._meta, '_name_map')
        self.assertFalse(hasattr(book._meta, '_name_map'))
        map2 = book._get_field_map()
        # after _meta.init_name_map(), the _name_map is created and cached.
        self.assertTrue(hasattr(book._meta, '_name_map'))

        self.assertEqual(map1, map2)

    def testNew(self):
        author = models.Author(name='MoYan')
        author.save()
        a = models.Author.objects.get(name='MoYan')
        self.assertTrue(a.pk)
        self.assertEqual(a.state, models.Author.DRAFT)

    def testCloneNoRelated(self):
        """
        class Cloneable _clone method.
        a clone has identical properties except vid
        """
        delattr(models.Book, '_clone_related')
        self.assertFalse(hasattr(models.Book, '_clone_related'))

        book = models.Book.objects.get(pk=1)
        last_save = book.last_save

        with manager.SwitchSchema('public'):
            n_books = models.Book.normal.all().count()

        book._clone()
        book = models.Book.objects.get(vid=1)

        with manager.SwitchSchema('public'):
            n_books_new = models.Book.normal.all().count()

        self.assertEqual(n_books, n_books_new - 1)

        self.assertEqual(book.pk, 1)
        self.assertEqual(last_save, book.last_save)

        clone = models.Book.objects.get(vid=2)
        self.assertEqual(clone.author, book.author)
        self.assertEqual(clone.object_id, book.object_id)

        setattr(models.Book, '_clone_related', ['review', 'galleries'])

    def testCloneRelated(self):
        """
        attributes registered in _clone_related should be cloned as well
        """
        self.assertTrue(hasattr(models.Book, '_clone_related'))

        book = models.Book.objects.get(vid=1)
        n_review = models.Review.objects.all().count()
        self.assertEqual(n_review, 2)
        n_gallery = models.Gallery.objects.all().count()
        self.assertEqual(n_gallery, 2)

        book._clone()
        clone = models.Book.objects.get(vid=2)
        book = models.Book.objects.get(vid=1)

        n_review = clone.review_set.all().count()
        self.assertEqual(n_review, 2)

        n_review = models.Review.objects.all().count()
        self.assertEqual(n_review, 4)

        n_gallery = models.Gallery.objects.all().count()
        self.assertEqual(n_gallery, 4)

    def testDeleteRelated(self):
        """
        related objects should be deleted as well
        """
        self.assertEqual(models.Book.objects.all().count(), 1)
        book = models.Book.objects.get(vid=1)

        self.assertEqual(models.Gallery.objects.all().count(), 2)
        self.assertEqual(models.Review.objects.all().count(), 2)

        book.delete()
        self.assertEqual(models.Book.objects.all().count(), 0)

        self.assertEqual(models.Gallery.objects.all().count(), 0)
        self.assertEqual(models.Review.objects.all().count(), 0)

    def testDeleteReverseM2M(self):
        no = models.NoReverse(name='test')
        no.save()
        with self.assertRaises(AssertionError):
            no.delete()

    def testDeleteVersion(self):
        """
        delete one version of an object should also delete all other versions
        """
        bp, bd = self._prepare_books()

        bp.delete()
        with manager.SwitchSchema('public'):
            self.assertFalse(models.Book.normal.filter(object_id=bd.object_id
                             ).exists())

        self.assertEqual(models.Gallery.objects.all().count(), 0)

    def testReverseM2MDeleteVersion(self):
        cartoon = models.Cartoon.objects.get(vid=1)
        cartoon.publish()

        with manager.SwitchSchema('public'):
            self.assertEqual(models.Cartoon.normal.all().count(), 2)


        klass = cartoon.get_version_class()
        ins = klass.normal.get(vid=2)
        ins.delete()

        self.assertEqual(models.Cartoon.normal.all().count(), 1)
        image = models.Image(pk=1)
        self.assertEqual(image.cartoons.all().count(), 1)

    def testDeleteWithM2M(self):
        cartoon = models.Cartoon.objects.get(vid=1)
        cartoon.publish()

        with manager.SwitchSchema('public'):
            self.assertEqual(models.Cartoon.normal.all().count(), 2)

            image = models.Image(pk=1)
            self.assertEqual(image.cartoons.all().count(), 1)

            cartoon.delete()
            self.assertEqual(image.cartoons.all().count(), 0)

    def testChangeRelated(self):
        """
        change related items of an object version won't affect other versions
        """
        bp, bd = self._prepare_books()

        with manager.SwitchSchema('draft'):
            bd_reviews = list(bd.review_set.all())
            bd_gallery = list(bd.galleries.all())

        # change related object
        bd_reviews[0].text = 'changed'
        bd_reviews[0].save()
        bd_gallery[0].name = 'changed'
        bd_gallery[0].save()

        self.assertTrue(bd.review_set.filter(text='changed').exists())
        self.assertTrue(bd.galleries.filter(name='changed').exists())

        with manager.SwitchSchema('published'):
            self.assertEqual(bp.review_set.all().count(), 2)
            self.assertEqual(bp.galleries.all().count(), 2)
            self.assertFalse(bp.review_set.filter(text='changed').exists())
            self.assertFalse(bp.galleries.filter(name='changed').exists())

    def testAddRelated(self):
        """
        add related item to an object version won't affect other versions
        """
        bp, bd = self._prepare_books()
        # add relationship
        g = models.Gallery(name='newly added')
        g.save()
        bp.galleries.add(g)

        with manager.SwitchSchema('published'):
            self.assertTrue(bp.galleries.filter(name='newly added').exists())
            self.assertEqual(bp.galleries.all().count(), 3)

        with manager.SwitchSchema('draft'):
            self.assertFalse(bd.galleries.filter(name='newly added').exists())
            self.assertEqual(bd.galleries.all().count(), 2)

        self.assertEqual(models.Gallery.objects.all().count(), 5)

    def testRelatedName(self):
        author = models.Author.objects.get(vid=1)
        self.assertTrue(hasattr(author, 'works_version'))

    def testPublishAuthor(self):
        """
        publish is actually, make a clone of draft, and change the state
        of the clone to PUBLISHED
        """
        author = models.Author.objects.get(vid=1)
        self.assertEqual(author.state, models.Author.DRAFT)
        old_vid = author.vid

        author.publish()
        self.assertEqual(author.state, models.Author.PUBLISHED)
        self.assertNotEqual(author.vid, old_vid)

        author = models.Author.objects.get(vid=old_vid)
        self.assertEqual(author.state, models.Author.DRAFT)

    def testRegisterRelated(self):
        original = models.Book._clone_related
        delattr(models.Book, '_clone_related')
        models.Book.register_related('test')
        related = models.Book._clone_related
        self.assertEqual(related, ['test'])

        models.Book._clone_related = ('test',)
        models.Book.register_related('test2')
        related = models.Book._clone_related
        self.assertEqual(related, ['test', 'test2'])

        models.Book._clone_related = original

    def testGetVersion(self):
        author = models.Author.objects.get(pk=1)
        self.assertEqual(author.get_version(state=models.Author.PUBLISHED),
                                             None)

    def testPublishBook(self):
        from django.contrib.auth.models import User
        u = User.objects.create(username='admin')

        book = models.Book.objects.get(vid=1)
        book.publish(user=u)
        bd = models.Book.objects.get(object_id=book.object_id,
                                     state=models.Book.DRAFT)
        bp = book

        self.assertEqual(bp.user_published, 'admin')

        self._check_different_book_versions(bd, bp)

    def testUnPublish(self):
        book = models.Book.objects.get(vid=1)
        klass = book.get_version_class()
        book.publish()
        self.assertEqual(klass.normal.filter().count(), 2)
        self.assertTrue(book.is_published)
        self.assertEqual(book.state, models.Book.PUBLISHED)

        book = models.Book.objects.get(vid=1)
        book.unpublish()
        self.assertEqual(klass.normal.filter().count(), 2)
        self.assertFalse(book.is_published)

    def testUnPublishWithScheduled(self):
        book = models.Book.objects.get(vid=1)
        klass = book.get_version_class()

        # schedule to publish
        t = timezone.now() + datetime.timedelta(days=7)
        book.publish(when=t)
        self.assertEqual(klass.normal.all().count(), 2)

        book = models.Book.objects.get(vid=1)
        book.unpublish()
        # make sure scheduled items get deleted
        self.assertFalse(klass.normal.filter(object_id=book.object_id,
                         state=models.Book.SCHEDULED).exists())
        self.assertEqual(klass.normal.all().count(), 1)

    def testPublishWithPublishedAndScheduled(self):
        book = models.Book.objects.get(vid=1)
        klass = book.get_version_class()

        # publish the draft
        book.publish()
        self.assertEqual(klass.normal.all().count(), 2)
        self.assertTrue(klass.normal.filter(
                                state=models.Book.PUBLISHED).exists())

        # schedule the draft to be published in future
        book = models.Book.objects.get(vid=1)
        t = timezone.now() + datetime.timedelta(days=20)
        book.publish(when=t)
        self.assertEqual(klass.normal.all().count(), 3)
        self.assertTrue(klass.normal.filter(
                                state=models.Book.SCHEDULED).exists())

        # try publish the draft again; it will archive the item published above
        # and publish the current one
        book = models.Book.objects.get(vid=1)
        book.publish(when=timezone.now())
        self.assertEqual(klass.normal.all().count(), 4)
        self.assertTrue(klass.normal.filter(
                                    state=models.Book.ARCHIVED).exists())

    def testPublishWithScheduledOnly(self):
        book = models.Book.objects.get(vid=1)
        klass = book.get_version_class()

        # schedule the draft to be published in future
        book = models.Book.objects.get(vid=1)
        t = timezone.now() + datetime.timedelta(days=7)
        book.publish(when=t)
        self.assertEqual(klass.normal.all().count(), 2)
        self.assertTrue(klass.normal.filter(
                                    state=models.Book.SCHEDULED).exists())

        # the time stamp info in draft and scheduled items are identical
        draft = models.Book.objects.get(vid=1)
        self.assertEqual(draft.last_scheduled, book.last_scheduled)
        self.assertEqual(draft.date_published, t)
        self.assertEqual(book.date_published, t)

        # try publish the draft again; it should only overwrite the item
        # scheduled item above.
        draft.publish()
        self.assertEqual(klass.normal.all().count(), 2)
        self.assertFalse(klass.normal.filter(
                                    state=models.Book.PUBLISHED).exists())

        # if you want to really publish it. gotta provide "when"
        book = models.Book.objects.get(vid=1)
        book.publish(when=timezone.now())
        self.assertTrue(klass.normal.filter(
                                    state=models.Book.PUBLISHED).exists())

    def testMakeDraft(self):
        book = models.Book.objects.get(vid=1)
        self.assertEqual(book.name, 'Book1')

        # draft cannot make draft -- return nothing inside make_draft function.
        with  self.assertRaises(AssertionError):
            book.make_draft()

        klass = book.get_version_class()
        book = klass.normal.get(vid=1)
        book.make_draft()
        self.assertEqual(models.Book.objects.filter(
                                        object_id=book.object_id).count(), 1)

        book = klass.normal.get(vid=1)
        book.publish()

        # prepare a draft for deleting when calling make_draft
        draft = klass.normal.get(object_id=book.object_id,
                                 state=models.Book.DRAFT)
        self.assertEqual(draft.last_scheduled, draft.last_save)
        draft.name = 'book2'
        draft.save()
        self.assertTrue(klass.normal.filter(name='book2').exists())

        # need to get the object again to get updated last_save value, coz the
        # one cached by django is not updated.
        draft = klass.normal.get(object_id=book.object_id,
                                 state=models.Book.DRAFT)
        self.assertEqual(draft.last_scheduled, book.last_scheduled)
        self.assertTrue(draft.last_scheduled < draft.last_save)

        book = klass.normal.get(object_id=book.object_id,
                                state=models.Book.PUBLISHED)
        book.make_draft()
        # make sure the old draft get deleted
        self.assertFalse(klass.normal.filter(name='book2').exists())

        # make sure the underlying two versions of book are "same"
        manager.deactivate()
        bd = models.Book.objects.get(object_id=book.object_id,
                                     state=models.Book.DRAFT)
        bp = models.Book.objects.get(object_id=book.object_id,
                                     state=models.Book.PUBLISHED)
        manager.activate('draft')

        self.assertEqual(bd.name, 'Book1')
        self._check_different_book_versions(bd, bp)

    def testRevert(self):
        """
        update the draft; revert to the archived;
        the update should be abolished.
        """
        obp, obd = self._prepare_books()
        obd.publish()
        klass = obp.get_version_class()

        with manager.SwitchSchema('public'):
            bp = klass.normal.get(object_id=obp.object_id,
                                  state=models.Book.PUBLISHED)
            bd = klass.normal.get(object_id=obp.object_id,
                                  state=models.Book.DRAFT)
            ba = klass.normal.get(object_id=obp.object_id,
                                  state=models.Book.ARCHIVED)

        bd.name = 'the sea'
        bd.save()
        self.assertEqual(bd.name, 'the sea')
        self.assertEqual(bp.name, 'Book1')
        self.assertEqual(ba.name, 'Book1')

        ba.make_draft()
        with manager.SwitchSchema('public'):
            self.assertEqual(models.Book.normal.all().count(), 3)
            bp2 = models.Book.normal.get(object_id=obp.object_id,
                                          state=models.Book.PUBLISHED)
            bd2 = models.Book.normal.get(object_id=obp.object_id,
                                          state=models.Book.DRAFT)
            ba2 = models.Book.normal.get(object_id=obp.object_id,
                                          state=models.Book.ARCHIVED)

        # old draft gets deleted,
        self.assertFalse(models.Book.objects.filter(vid=1).exists())
        # new draft generated
        self.assertEqual(bd2.name, 'Book1')
        #other versions stay same
        self.assertEqual(bp2.name, 'Book1')
        self.assertEqual(ba2.name, 'Book1')

    def testDraftRelated(self):
        """
        get draft, and published. add new gallery item to draft, and publish
        it then revert back.

        remove gallery item from draft; publish it; revert back;
        """
        obp, obd = self._prepare_books()
        klass = obp.get_version_class()

        bp = klass.normal.get(object_id=obp.object_id,
                              state=models.Book.PUBLISHED)
        bd = klass.normal.get(object_id=obp.object_id, state=models.Book.DRAFT)

        self.assertEqual(models.Gallery.objects.all().count(), 4)
        self.assertEqual(bd.vid, 1)

        # change draft
        g = models.Gallery(name='old man')
        g.save()
        bd.galleries.add(g)
        self.assertEqual(models.Gallery.objects.all().count(), 5)

        # change should occur only in draft
        self.assertEqual(bp.galleries.all().count(), 2)
        self.assertFalse(bp.galleries.filter(name='old man').exists())
        self.assertEqual(bd.galleries.all().count(), 3)
        self.assertTrue(bd.galleries.filter(name='old man').exists())

        # publish the changed draft; change should now in published version
        bd.publish()
        bp2 = klass.normal.get(object_id=obp.object_id,
                               state=models.Book.PUBLISHED)
        klass.normal.filter(object_id=obp.object_id,
                               state=models.Book.DRAFT).exists()
        ba2 = klass.normal.get(object_id=obp.object_id,
                               state=models.Book.ARCHIVED)
        self.assertEqual(models.Gallery.objects.all().count(), 8)
        self.assertEqual(bp2.galleries.all().count(), 3)
        self.assertTrue(bp2.galleries.filter(name='old man').exists())
        # meanwhile, published get archived
        self.assertEqual(ba2.vid, bp.vid)

        # revert archived back to draft
        ba2.make_draft()
        self.assertEqual(klass.normal.all().count(), 3)
        self.assertEqual(models.Gallery.objects.all().count(), 7)
        bp3 = klass.normal.get(object_id=obp.object_id,
                               state=models.Book.PUBLISHED)
        bd3 = klass.normal.get(object_id=obp.object_id,
                               state=models.Book.DRAFT)
        ba3 = klass.normal.get(object_id=obp.object_id,
                               state=models.Book.ARCHIVED)
        self.assertEqual(bd3.galleries.all().count(), 2)
        self.assertFalse(bd3.galleries.filter(name='old man').exists())

        # remove one gallery item from draft
        g = bd3.galleries.filter(name='Gallery1')
        self.assertEqual(len(g), 1)
        bd3.galleries.remove(g[0])
        self.assertEqual(models.Gallery.objects.all().count(), 7)
        self.assertEqual(bd3.galleries.all().count(), 1)
        self.assertEqual(bp3.galleries.all().count(), 3)
        self.assertEqual(ba3.galleries.all().count(), 2)

        # publish the draft, we now have 1 published, 1 draft, and 2 archived
        bd3.publish()
        self.assertEqual(klass.normal.all().count(), 4)
        self.assertEqual(models.Gallery.objects.all().count(), 8)
        bp4 = klass.normal.get(object_id=obp.object_id,
                               state=models.Book.PUBLISHED)
        bd4 = klass.normal.get(object_id=obp.object_id,
                               state=models.Book.DRAFT)
        ba4 = klass.normal.get(object_id=obp.object_id, vid=bp3.vid)
        # now both the draft and published should have only 1 gallery item
        self.assertEqual(bp4.galleries.all().count(), 1)
        self.assertFalse(bp4.galleries.filter(name='Gallery1').exists())
        self.assertEqual(bd4.galleries.all().count(), 1)
        self.assertFalse(bd4.galleries.filter(name='Gallery1').exists())

        # revert back to the new archived status (ba4 is actually bp3)
        ba4.make_draft()
        self.assertEqual(klass.normal.all().count(), 4)
        self.assertEqual(models.Gallery.objects.all().count(), 10)

        bp5 = klass.normal.get(object_id=obp.object_id,
                               state=models.Book.PUBLISHED)
        bd5 = klass.normal.get(object_id=obp.object_id,
                               state=models.Book.DRAFT)
        # now the draft should havd 3 gallery items
        self.assertEqual(bd5.galleries.all().count(), 3)
        self.assertTrue(bd5.galleries.filter(name='Gallery1').exists())
        self.assertTrue(bd5.galleries.filter(name='old man').exists())
        # published is not affected
        self.assertEqual(bp5.galleries.all().count(), 1)
        self.assertTrue(bp5.galleries.filter(name='Gallery2').exists())

    def testMakeDraftWithoutDraft(self):
        # it is ok for published book to make draft, when there is no draft.
        book = models.Book.objects.get(vid=1)
        klass = book.get_version_class()
        book = klass.normal.get(vid=1)

        book.publish()
        draft = klass.normal.get(object_id=book.object_id,
                                 state=models.Book.DRAFT)
        draft.delete()

        self.assertTrue(klass.normal.filter(object_id=book.object_id,
                         state=models.Book.PUBLISHED).exists())
        book.make_draft()
        self.assertEqual(klass.normal.all().count(), 2)

    def testPurgeArchive(self):
        # create a few ARCHIVED versions
        for i in range(0, 10):
            book = models.Book.objects.get(vid=1)
            book.publish()

        # the underlying versions
        klass = book.get_version_class()
        self.assertEqual(klass.normal.filter(state=models.Book.ARCHIVED
                                             ).count(), 9)
        self.assertEqual(klass.normal.filter(state=models.Book.DRAFT
                                             ).count(), 1)
        self.assertEqual(klass.normal.filter(state=models.Book.PUBLISHED
                                             ).count(), 1)

        # make sure only NUM_KEEP_ARCHIVED (5) number of ARCHIVED are kept
        book.purge_archives()
        self.assertEqual(klass.normal.filter(state=models.Book.ARCHIVED
                                             ).count(), 5)
        self.assertEqual(models.Gallery.objects.all().count(), 14)

    def testStatus1(self):
        book = models.Book.objects.get(vid=1)
        self.assertEqual(book.state, models.Book.DRAFT)
        self.assertEqual(book.status_line(), "Draft saved: 08/30/2012")

        # schedule to publish in future. should get status as Scheduled.
        book.publish(when=timezone.now() + datetime.timedelta(days=7))
        draft = models.Book.objects.get(vid=1)

        self.assertEqual(draft.last_save, draft.last_scheduled)
        self.assertFalse(draft.v_last_save)  # v_last_save empty
        status = "%s: %s" % ('Publish Scheduled',
                    formats.date_format(draft.date_published,
                                        "SHORT_DATE_FORMAT"))
        self.assertEqual(status, draft.status_line())

        # publish it now. should get status as Published
        when = timezone.now()
        book = models.Book.objects.get(vid=1)
        book.publish(when=when)
        draft2 = models.Book.objects.get(vid=1)

        self.assertEqual(draft2.last_save, draft2.last_scheduled)
        self.assertEqual(draft2.last_save, draft2.v_last_save)
        status = "%s: %s" % ('Published',
                    formats.date_format(draft2.date_published,
                                        "SHORT_DATE_FORMAT"))
        self.assertEqual(status, draft2.status_line())
        self.assertEqual(draft2.date_published, when)

        # schedule to publish in future again. should get status as Scheduled
        book = models.Book.objects.get(vid=1)
        book.publish(when=timezone.now() + datetime.timedelta(days=7))
        draft = models.Book.objects.get(vid=1)
        self.assertEqual(draft.last_save, draft.last_scheduled)
        self.assertTrue(draft.last_scheduled > draft.v_last_save)
        status = "%s: %s" % ('Publish Scheduled',
                    formats.date_format(draft.date_published,
                                        "SHORT_DATE_FORMAT"))
        self.assertEqual(status, draft.status_line())

    def testStatus2(self):
        book = models.Book.objects.get(vid=1)
        self.assertEqual(book.state, models.Book.DRAFT)
        self.assertEqual(book.status_line(), "Draft saved: 08/30/2012")

        book.publish()
        draft = models.Book.objects.get(vid=1)
        self.assertEqual(book.v_last_save, draft.v_last_save)
        self.assertEqual(draft.last_save, draft.last_scheduled)
        self.assertEqual(draft.last_save, draft.v_last_save)
        status = "%s: %s" % ('Published',
                    formats.date_format(draft.last_save,
                                        "SHORT_DATE_FORMAT"))
        self.assertEqual(status, book.status_line())

    def testSwitchSchema(self):
        book = models.Book.objects.get(vid=1)
        book.publish()
        self.assertEqual(models.Book.normal.all().count(), 1)
        with manager.SwitchSchema('public'):
            self.assertEqual(models.Book.normal.all().count(), 2)

        self.assertEqual(models.Book.normal.all().count(), 1)
        manager.deactivate()
        self.assertEqual(models.Book.normal.all().count(), 2)

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
        with  self.assertRaises(ValidationError):
            a2.validate_unique()

        # multiple versions are not affected (can co-exists)
        klass = a1.get_version_class()
        self.assertEqual(klass.normal.filter(object_id=a1.object_id
                                             ).count(), 1)
        a1.publish()
        self.assertEqual(klass.normal.filter(object_id=a1.object_id
                                             ).count(), 2)
        self.assertTrue(klass.normal.filter(object_id=a1.object_id,
                                            state=a1.DRAFT).exists())
        self.assertTrue(klass.normal.filter(object_id=a1.object_id,
                                            state=a1.PUBLISHED).exists())
        a1.validate_unique()

    def testCustomBaseModel(self):
        """
        custom base_model; defined by _base_model in Meta;
        should turn on 'should_save_base' to save fields in _base_model.
        """
        gun = models.Gun()
        self.assertEqual(gun._meta._base_model, models.CustomModel)

        # should have all the fields, including the one from _base_model
        self.assertTrue(hasattr(gun, 'created_date'))
        self.assertTrue(hasattr(gun, 'v_last_save'))
        self.assertTrue(hasattr(gun, 'reg_number'))
        self.assertTrue(hasattr(gun, 'is_published'))
        self.assertFalse(hasattr(gun, 'none_exist_field'))

        self.assertTrue(hasattr(gun, 'should_save_base'))

        self.assertEqual(gun.should_save_base, False)

        # should be created normally
        gun.name = 'AK47'
        gun.save()

        gun = models.Gun.objects.get(name='AK47')
        self.assertEqual(gun.object_id, 1)
        self.assertFalse(gun.reg_number)

        self.assertEqual(gun.should_save_base, False)
        gun.reg_number = 'A1234'
        gun.save()
        gun = models.Gun.objects.get(vid=1)
        # not get saved
        self.assertFalse(gun.reg_number)

        gun.should_save_base = True
        gun.reg_number = 'B3210'
        gun.save()
        gun = models.Gun.objects.get(vid=1)
        # should get saved now, since should_save_base is on
        self.assertEqual(gun.reg_number, 'B3210')


class TransactionSwitchTests(TestCase):
    fixtures = ('test_data.json',)

    def setUp(self):
        manager.activate('draft')

    def tearDown(self):
        manager.deactivate()

    def testDeleteWithNormal(self):
        author = models.Author.objects.get(vid=1)
        author_id = author.pk
        author.publish()

        cartoon = models.Cartoon.objects.get(vid=1)
        self.assertEqual(cartoon.author, author)
        cartoon.publish()

        book = models.Book.objects.get(vid=1)
        book.publish()

        book2 = models.Book(name='test', author_id=2)
        book2.save()

        with manager.SwitchSchema('public'):
            self.assertEqual(models.Author.normal.filter(associates__pk=2).count(), 2)
            self.assertEqual(models.Cartoon.normal.filter(author=author).count(), 2)
            self.assertEqual(models.Cartoon.normal.filter(author__isnull=True).count(), 0)

        # Switch to draft mode to restrict what the ORM
        # will normally see
        with manager.SwitchSchema('draft'):
            self.assertEqual(models.Book.objects.filter(author=author).count(), 1)
            self.assertEqual(models.Gallery.objects.filter(book__author=author).count(), 2)
            self.assertEqual(models.Review.objects.filter(book__author=author).count(), 2)

            book = models.Book.objects.get(vid=1)
            self.assertEqual(book.author, author)
            author.delete()

        with manager.SwitchSchema('public'):
            self.assertEqual(models.Author.normal.filter(associates__pk=2).count(), 0)
            self.assertFalse(models.Author.normal.filter(pk=author_id).exists())
            self.assertEqual(models.Cartoon.normal.filter(author_id=author_id).count(), 0)
            self.assertEqual(models.Cartoon.normal.filter(author__isnull=True).count(), 2)
            self.assertEqual(models.Book.normal.all().count(), 1)
            self.assertEqual(models.Review.objects.all().count(), 0)
            self.assertEqual(models.Gallery.objects.all().count(), 0)

class ManagerTests(TestCase):
    fixtures = ('test_data.json',)

    def testActivate(self):
        schema = manager.get_schema()
        self.assertEqual(schema, None)

        book = models.Book.objects.get(vid=1)
        book.publish()
        self.assertTrue(models.Book.objects.filter(state=models.Book.PUBLISHED,
                        object_id=book.object_id))

        manager.activate('draft')
        self.assertFalse(models.Book.objects.filter(
                                    state=models.Book.PUBLISHED,
                                    object_id=book.object_id))
        schema = manager.get_schema()
        self.assertEqual(schema, 'draft')

        manager.deactivate()
        self.assertTrue(models.Book.objects.filter(state=models.Book.PUBLISHED,
                        object_id=book.object_id))
        schema = manager.get_schema()
        self.assertEqual(schema, None)

    def testLazyEval(self):
        schema = manager.get_schema()
        self.assertEqual(schema, None)
        book = models.Book.objects.get(vid=1)
        book.publish()

        manager.activate('published')
        qs = models.Book.objects.filter(pk=1)
        self.assertEqual(qs.count(), 1)
        manager.deactivate()

        manager.activate('draft')
        self.assertEqual(qs.count(), 1)
        manager.deactivate()

        self.assertEqual(qs.count(), 2)
