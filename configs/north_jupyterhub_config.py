# KIT addition to the JupyterHub config of ghcr.io/fairmat-nfdi/nomad-north (Docker variant).
#
# Why: with NOMAD v2's new NORTH hub, tool containers no longer get NOMAD_CLIENT_USER,
# NOMAD_CLIENT_ACCESS_TOKEN and NOMAD_CLIENT_URL. Our Voila apps need them to call the
# NOMAD API (hysprint_utils.access_token.get_token). This file loads the image's own
# config unchanged and only adds these variables when a tool is started. The logic
# mirrors FAIRmat's fix for the Kubernetes hub:
#   https://github.com/FAIRmat-NFDI/nomad-north/pull/14 (issue #10)
# which was not available for the Docker hub image (images/hub) yet.
#
# ---------------------------------------------------------------------------------
# TODO(remove workaround): when updating the NORTH image tag in docker-compose.yaml
# ---------------------------------------------------------------------------------
# 1. Check whether the new image sets the variables itself:
#      docker run --rm --entrypoint grep ghcr.io/fairmat-nfdi/nomad-north:<new tag> \
#        -nE "NOMAD_CLIENT|app_token" /srv/jupyterhub/jupyterhub_config.py
# 2. If yes: delete this file and, in docker-compose.yaml (service `north`), remove the
#    `command:` line and the volume mount of this file. Nothing else is needed, the
#    variable names are the same, so the Voila apps keep working.
# 3. If no: keep it, but check that /srv/jupyterhub/jupyterhub_config.py still exists
#    and still sets `c.JupyterHub.spawner_class`. Otherwise the hub fails to start
#    (`docker logs nomad_oasis_north`).
# Keeping this file after an upstream fix does not break anything, it only sets the
# same variables a second time.

import asyncio
import os

import requests

load_subconfig('/srv/jupyterhub/jupyterhub_config.py')  # noqa: F821

nomad_api_url = os.environ.get('NOMAD_API_URL', 'http://app:8000/backend/api/v1')
nomad_api_timeout = float(os.environ.get('NOMAD_API_TIMEOUT', 10))
nomad_app_token_expires_in = int(os.environ.get('NOMAD_APP_TOKEN_EXPIRES_IN', 24 * 3600))

_NORTHSpawner = c.JupyterHub.spawner_class  # noqa: F821


def _get_app_token(access_token):
    response = requests.get(
        f'{nomad_api_url}/auth/app_token',
        params={'expires_in': nomad_app_token_expires_in},
        headers={'Authorization': f'Bearer {access_token}'},
        timeout=nomad_api_timeout,
    )
    response.raise_for_status()
    return response.json()['app_token']


class KITNORTHSpawner(_NORTHSpawner):
    async def start(self):
        access_token = self.user_options.get('access_token')
        if self.name and access_token:
            try:
                app_token = await asyncio.to_thread(_get_app_token, access_token)
            except Exception as e:
                # Start the tool anyway, only API access from inside it will fail.
                self.log.warning(f'[KIT] Could not get a NOMAD app token for {self.user.name}: {e}')
            else:
                self.environment['NOMAD_CLIENT_USER'] = self.user.name
                self.environment['NOMAD_CLIENT_ACCESS_TOKEN'] = app_token
                self.environment['NOMAD_CLIENT_URL'] = nomad_api_url
                self.log.info(f'[KIT] Set NOMAD_CLIENT_* for {self.user.name}:{self.name}')
        return await super().start()


c.JupyterHub.spawner_class = KITNORTHSpawner  # noqa: F821
