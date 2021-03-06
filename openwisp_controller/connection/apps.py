from celery.task.control import inspect
from django.apps import AppConfig
from django.db import transaction
from django.db.models.signals import post_save
from django.utils.translation import ugettext_lazy as _
from swapper import load_model

from ..config.signals import config_modified

_TASK_NAME = 'openwisp_controller.connection.tasks.update_config'


class ConnectionConfig(AppConfig):
    name = 'openwisp_controller.connection'
    label = 'connection'
    verbose_name = _('Network Device Credentials')

    def ready(self):
        """
        connects the ``config_modified`` signal
        to the ``update_config`` celery task
        which will be executed in the background
        """
        config_modified.connect(
            self.config_modified_receiver, dispatch_uid='connection.update_config'
        )
        Config = load_model('config', 'Config')
        Credentials = load_model('connection', 'Credentials')
        post_save.connect(
            Credentials.auto_add_credentials_to_device,
            sender=Config,
            dispatch_uid='connection.auto_add_credentials',
        )

    @classmethod
    def config_modified_receiver(cls, **kwargs):
        device = kwargs['device']
        conn_count = device.deviceconnection_set.count()
        # if device has no connection specified stop here
        if conn_count < 1:
            return
        transaction.on_commit(lambda: cls._launch_update_config(device.pk))

    @classmethod
    def _launch_update_config(cls, device_pk):
        """
        Calls the background task update_config only if
        no other tasks are running for the same device
        """
        if cls._is_update_in_progress(device_pk):
            return
        from .tasks import update_config

        update_config.delay(device_pk)

    @classmethod
    def _is_update_in_progress(cls, device_pk):
        active = inspect().active()
        if not active:
            return False
        # check if there's any other running task before adding it
        for task_list in active.values():
            for task in task_list:
                if task['name'] == _TASK_NAME and str(device_pk) in task['args']:
                    return True
        return False
