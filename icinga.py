from datetime import datetime
from getpass import getuser

from requests import get, post


class IcingaItem(object):
    def __init__(self, json):
        self.downtime_depth = int(json['attrs']['downtime_depth'])
        self.state = int(json['attrs']['state'])
        self.state_type = int(json['attrs']['state_type'])
        self.type = json['type']

        if self.type == 'Service':
            self.host_name = json['attrs']['host_name']
            self.service_name = json['attrs']['display_name']
        else:
            if self.state != 0:
                self.state = 2
            self.host_name = json['attrs']['display_name']
            self.service_name = '-- HOST --'

        self.output_lines = json['attrs'].get('last_check_result', {}).get('output', '').splitlines()

    def __lt__(self, other):
        if self.state == other.state:
            if self.host_name == other.host_name:
                return self.service_name < other.service_name
            else:
                return self.host_name < other.host_name
        else:
            return -self.state < -other.state

    def get_filter(self):
        f = f'match("{self.host_name}", host.name)'
        if self.type == 'Service':
            f += f' && match("{self.service_name}", service.name)'
        return f

    def get_line_to_show(self, len_col1):
        prefix = 'D  ' if self.downtime_depth > 0 else '   '
        host_name = prefix + self.host_name + ' ' * (len_col1 - len(self.host_name))
        return f'{host_name}  {self.service_name}'


class Icinga(object):
    def _api(self, endpoint):
        return self.settings['base_url'] + '/api/v1/' + endpoint

    def get_current_state(self):
        r = get(self._api('objects/hosts'), auth=self.settings['auth'])
        r.raise_for_status()
        hosts = r.json()

        r = get(self._api('objects/services'), auth=self.settings['auth'])
        r.raise_for_status()
        services = r.json()

        return {
            'hosts': [IcingaItem(i) for i in hosts['results']],
            'services': [IcingaItem(i) for i in services['results']],
        }

    def set_downtime(self, items, comment, duration):
        if not comment:
            comment = 'go away'

        if duration.endswith('s'):
            seconds = int(duration[:-1])
        elif duration.endswith('m'):
            seconds = int(duration[:-1]) * 60
        elif duration.endswith('h'):
            seconds = int(duration[:-1]) * 60 * 60
        elif duration.endswith('d'):
            seconds = int(duration[:-1]) * 60 * 60 * 24
        else:
            seconds = 2 * 60 * 60

        start_time = datetime.now().timestamp()
        end_time = start_time + seconds

        # TODO Parallelize.
        for i in items:
            data = {
                'author': getuser(),
                'comment': comment,
                'start_time': start_time,
                'end_time': end_time,
                'type': i.type,
                'filter': i.get_filter(),
                'child_options': 'DowntimeTriggeredChildren',
            }
            r = post(
                self._api('actions/schedule-downtime'),
                auth=self.settings['auth'],
                headers={'Accept': 'application/json'},
                json=data,
            )
