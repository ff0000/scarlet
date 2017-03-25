#!/usr/bin/python
import os
import sys
import argparse
import importlib
import imp

import django
from django.conf import settings


def setup_test_environment(settings_overide, with_scarlet_blog=False):
    """
    Specific settings for testing
    """
    apps = [
        'django.contrib.auth',
        'django.contrib.contenttypes',
        'django.contrib.humanize',
        'django.contrib.messages',
        'django.contrib.sessions',
        'django.contrib.sites',
        'django.contrib.staticfiles',
        'scarlet.cms',
        'scarlet.assets',
        'scarlet.accounts',
        'scarlet.versioning',
        'scarlet.scheduling',
        'taggit',
        'tests.version_models',
        'tests.version_twomodels',
        'tests.cms_bundles',
    ]

    urls = 'tests.cms_bundles.urls'
    if with_scarlet_blog:
        apps.append('scarlet_blog.blog')
        apps.append('scarlet_blog.galleries')
        apps.append('scarlet_blog.comments')

    settings_dict = {
        'SECRET_KEY': "Please do not spew DeprecationWarnings",
        'SITE_ID': 1,
        'INSTALLED_APPS': apps,
        'STATIC_URL': '/static/',
        'ROOT_URLCONF': urls,
        'USE_TZ': True,
        'DATABASES': {
            'default': {
                'ENGINE': 'scarlet.versioning.postgres_backend',
                'NAME': 'cms',
                'USER': '',
                'PASSWORD': '',
                'HOST': 'localhost',
                'PORT': '',
            },
        },
        'MIDDLEWARE_CLASSES': (
            'django.contrib.sessions.middleware.SessionMiddleware',
            'django.contrib.auth.middleware.AuthenticationMiddleware',
            'django.contrib.messages.middleware.MessageMiddleware'
        )
    }

    if settings_overide:
        settings_dict.update(settings_overide)

    settings.configure(**settings_dict)


def runtests(settings_overide, test_args):
    """
    Build a test environment and a test_runner specifically for scarlet testing

    allows a settings overide file and runs scarlet blog tests
    if that module is present in the environment
    """

    parent = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, parent)
    scarlet_root = os.path.abspath(os.path.join(parent, '..'))
    sys.path.insert(0, scarlet_root)

    settings_dict = {}
    if settings_overide:
        mod = importlib.import_module(settings_overide)
        for s in dir(mod):
            if s == s.upper():
                settings_dict[s] = getattr(mod, s)

    with_scarlet_blog = False
    if not test_args:
        test_args = ['tests.cms_bundles', 'tests.version_models', 'tests.version_twomodels']
        try:
            imp.find_module('scarlet_blog')
            test_args.append('blog')
            with_scarlet_blog = True
        except ImportError:
            with_scarlet_blog = False

    elif 'blog' in test_args:
        with_scarlet_blog = True

    setup_test_environment(settings_dict, with_scarlet_blog=with_scarlet_blog)
    django.setup()

    from django.test.utils import get_runner
    def run_tests(test_args, verbosity, interactive):
        runner = get_runner(settings)()
        return runner.run_tests(test_args)

    failures = run_tests(test_args, verbosity=1, interactive=True)
    sys.exit(failures)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--settings", default='')
    parser.add_argument('args', nargs=argparse.REMAINDER)
    args = parser.parse_args()

    runtests(args.settings, args.args)
