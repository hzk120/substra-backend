from django.conf import settings


class LocalRequest(object):

    def is_secure(self):
        return not getattr(settings, 'DEBUG')

    def get_host(self):
        return getattr(settings, 'SITE_HOST')
